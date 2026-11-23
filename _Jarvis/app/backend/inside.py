"""
inside.py -- what is inside Jarvis, counted live, for the showcase's
"Inside Jarvis" tab (web/js/inside.js).

Five parts, each its own answer with its own signature, so a page that
already holds a part is sent nothing new for it and redraws nothing:

  events    every bank entry, oldest first: the Sunflower
  zoom      every live recording, by project and animal: Powers of Ten
  versions  every CHANGELOG entry's outline and the tools it names, and
            the commits on each day: the Gyrus
  modules   every backend and front-end module, what calls what, and the
            lines of code by language: the Connectome
  calls     every candidate in every curation set, by kind of set, who made
            the last call and what it was: the River

and `totals`, the numbers the page counts up, worked out from the parts.

It is adaptive by construction: a signature is cheap (a directory pass, a
file's mtime, git's HEAD), and a part whose signature moved is worked out
again in the background while the page keeps the copy it has. Nothing here
writes to GUI_logs except the derived copy in GUI_logs/.cache/inside/ (git
ignores .cache), which is what lets the tab draw at once after a restart.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime

from . import feed
from .paths import APP_DIR, LOGS_DIR, REPO_ROOT

WIN = sys.platform == "win32"
_NO_WINDOW = 0x08000000 if WIN else 0

PARTS = ("events", "zoom", "versions", "modules", "calls")
CACHE = os.path.join(LOGS_DIR, ".cache", "inside", "census.json")
CHANGELOG = os.path.join(APP_DIR, "CHANGELOG.md")
# Where the app's history lives in git, under every name it has had.
GIT_PATHS = ("_Jarvis", "BARRY GUI")

# Counted as code: the folders a person writes in, never the recorded data.
CODE_DIRS = ("backend", "web", "tools", "docs", "supabase")
CODE_EXTS = {".py": "Python", ".js": "JavaScript", ".html": "HTML",
             ".css": "CSS", ".md": "Markdown", ".sql": "SQL", ".m": "MATLAB",
             ".ps1": "PowerShell"}
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "baseline"}

# The tools a version can name, as the ToolKit and the patch notes spell
# them. A version's mossy fibres in the Gyrus run to the ones it names.
TOOLS = ("Incisor", "Checkup", "Braces", "Root Canal", "X-ray", "Doppler",
         "Spotter", "Eye", "Junction", "Panning", "Lock", "Spark", "Coupling",
         "Circuit", "Drift", "Horizon", "Panorama", "Braid", "Monolith",
         "StrataScope", "Xplorefinder", "Sessions", "Event Bank", "Storyboard",
         "Figure builder", "Tooth Fairy", "Prospector", "Hater of AI", "VACC",
         "Kilosort")
_TOOL_RE = [(i, re.compile(r"(?<![\w-])" + re.escape(t) + r"(?![\w-])"))
            for i, t in enumerate(TOOLS)]

HOOKS = {"reg": None, "bank": None, "curate": None, "ai_labels": None}
_LOCK = threading.Lock()
_STATE = {"parts": {}, "sigs": {}, "busy": False, "errors": {}, "loaded": False}
_DONE = threading.Event()
_DONE.set()


def _hook(name):
    fn = HOOKS.get(name)
    return fn() if fn else None


# --- signatures: cheap, and each moves when its part would ---------------------

def _tree_sig(roots):
    count = newest = total = 0
    stack = list(roots)
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        if e.name not in SKIP_DIRS:
                            stack.append(e.path)
                        continue
                    if os.path.splitext(e.name)[1] not in CODE_EXTS:
                        continue
                    st = e.stat()
                    count += 1
                    newest = max(newest, st.st_mtime_ns)
                    total += st.st_mtime_ns + st.st_size
        except OSError:
            continue
    return "%d.%d.%d" % (count, newest, total)


def _git_head():
    """HEAD's commit, read from the files rather than by running git."""
    gd = os.path.join(REPO_ROOT, ".git")
    try:
        with open(os.path.join(gd, "HEAD"), encoding="utf-8") as fh:
            head = fh.read().strip()
        if not head.startswith("ref:"):
            return head
        ref = head[4:].strip()
        p = os.path.join(gd, *ref.split("/"))
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                return fh.read().strip()
        with open(os.path.join(gd, "packed-refs"), encoding="utf-8") as fh:
            for ln in fh:
                if ln.rstrip().endswith(" " + ref):
                    return ln.split(" ", 1)[0]
    except OSError:
        pass
    return ""


def _file_sig(path):
    try:
        st = os.stat(path)
        return "%d.%d" % (st.st_mtime_ns, st.st_size)
    except OSError:
        return "none"


def signatures():
    """Twelve hex characters a part, so the page can say what it holds in a
    query string."""
    raw = {}
    try:
        raw["events"] = repr(_hook("bank")._fingerprint())
    except Exception:                                    # noqa: BLE001
        raw["events"] = "?"
    try:
        raw["zoom"] = repr(_hook("reg").store.sessions.signature())
    except Exception:                                    # noqa: BLE001
        raw["zoom"] = "?"
    raw["versions"] = _file_sig(CHANGELOG) + "|" + _git_head()
    raw["modules"] = _tree_sig([os.path.join(APP_DIR, d) for d in CODE_DIRS])
    try:
        raw["calls"] = repr(_hook("curate").book.signature())
    except Exception:                                    # noqa: BLE001
        raw["calls"] = "?"
    return {k: hashlib.sha1(v.encode("utf-8")).hexdigest()[:12] for k, v in raw.items()}


# --- the parts ------------------------------------------------------------------------

def _epoch(stamp):
    if not stamp:
        return None
    try:
        return int(datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def part_events():
    """Every bank entry, oldest first. A pooled entry carries how many of its
    events came from each detector, so the page can colour them as found."""
    rows = []
    for e in _hook("bank").all():
        evs = e.get("events") or []
        kind = str(e.get("type") or "other")
        mix = None
        if kind == "pooled":
            c = Counter(str((v or {}).get("origin") or "both") for v in evs)
            mix = [c.get("incisor", 0), c.get("doppler", 0),
                   sum(n for k, n in c.items() if k not in ("incisor", "doppler"))]
        added = e.get("added") or {}
        rows.append([str(e.get("name") or e.get("id") or ""), kind, len(evs),
                     _epoch(added.get("at")), str(e.get("project") or ""),
                     len(e.get("versions") or []), mix])
    rows.sort(key=lambda r: r[3] or 0)
    return {"cols": ["name", "kind", "n", "at", "project", "versions", "mix"],
            "rows": rows}


def part_zoom():
    """Every live recording, grouped project > animal, with what its size is
    known from. Unknown lengths stay unknown: the page draws them as such."""
    rows = []
    for r in _hook("reg").live():
        def num(k):
            try:
                v = float(r.get(k) or 0)
                return v if v > 0 else None
            except (TypeError, ValueError):
                return None
        nch = num("n_channels")
        rows.append([str(r.get("project") or "Unfiled"), str(r.get("mouse") or "?"),
                     str(r.get("session") or ""), num("duration_s"),
                     int(nch) if nch else None, num("fs"),
                     str(r.get("label") or r.get("key") or "")])
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    return {"cols": ["project", "animal", "session", "seconds", "channels", "fs", "label"],
            "rows": rows}


_HEAD_RE = re.compile(r"^## (\d{4})\.(\d{2})\.(\d{2})\.(\d+)\s*[-—–]+\s*(.*)$")
_BULLET_RE = re.compile(r"^(\s*)[-*] \S")


def parse_changelog(text):
    """Every version: its name, day, title, words, the outline of its bullets
    (a list of children, each a list of its own) and the tools it names.

    The outline is the patch note's own structure, so a release with three
    headline changes, one of them in five parts, grows exactly that."""
    out, cur, stack = [], None, None
    for line in text.splitlines():
        m = _HEAD_RE.match(line)
        if m:
            cur = {"v": "%s.%s.%s.%s" % m.group(1, 2, 3, 4),
                   "day": "%s-%s-%s" % m.group(1, 2, 3),
                   "title": m.group(5).strip(), "tree": [], "words": 0, "_text": [line]}
            stack = [cur["tree"]]
            out.append(cur)
            continue
        if cur is None:
            continue
        cur["_text"].append(line)
        cur["words"] += len(line.split())
        b = _BULLET_RE.match(line)
        if b:
            depth = min(len(b.group(1).replace("\t", "  ")) // 2, len(stack) - 1)
            del stack[depth + 1:]
            node = []
            stack[depth].append(node)
            stack.append(node)
    for v in out:
        body = "\n".join(v.pop("_text"))
        v["tools"] = [i for i, rx in _TOOL_RE if rx.search(body)]
    out.reverse()                                        # oldest first
    return out


def _git(args, timeout=60):
    r = subprocess.run(["git", "-c", "core.longpaths=true"] + list(args), cwd=REPO_ROOT,
                       capture_output=True, timeout=timeout, creationflags=_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:300])
    return r.stdout.decode("utf-8", "replace")


def part_versions():
    with open(CHANGELOG, encoding="utf-8") as fh:
        versions = parse_changelog(fh.read())
    commits = {}
    try:
        days = Counter(_git(["log", "--format=%ad", "--date=short", "--"] + list(GIT_PATHS))
                       .split())
        commits = dict(sorted(days.items()))
    except Exception:                                    # noqa: BLE001
        commits = {}
    return {"tools": list(TOOLS), "versions": versions, "commits": commits}


_PY_FROM_DOT = re.compile(r"^from \.(\w*) import (\([^)]*\)|[^\n]+)", re.M)
_ROUTE_RE = re.compile(r"@app\.(?:route|get|post)\(\s*[\"']([^\"']+)[\"']")
_API_RE = re.compile(r"[\"'`](/api/[A-Za-z0-9_/\-.]*)")
_JS_DEF = re.compile(r"\b(?:BARRY|B)\.([A-Za-z_]\w*)\s*=(?!=)")
_JS_USE = re.compile(r"\b(?:BARRY|B)\.([A-Za-z_]\w*)")


def _import_items(names):
    """`(a as b, c)` -> [("a", "b"), ("c", "c")]."""
    out = []
    for item in names.replace("(", "").replace(")", "").split(","):
        item = item.split("#", 1)[0].strip()
        if not item:
            continue
        parts = item.split()
        name = parts[0]
        out.append((name, parts[2] if len(parts) == 3 and parts[1] == "as" else name))
    return out


def _purpose(name, text):
    """What a module says it is for: the first sentence of its opening
    comment, whole. A line of a wrapped paragraph is half a sentence."""
    head = text[:4000]
    m = re.search(r'"""(.*?)"""', head, re.S) if name.endswith(".py") else \
        re.search(r"/\*(.*?)\*/", head, re.S)
    if not m:
        return ""
    para, started = [], False
    for ln in m.group(1).splitlines():
        ln = ln.strip().lstrip("*#/").strip()
        if re.fullmatch(r"[=\-~*_ ]*", ln):
            if started and not ln:
                break
            continue
        started = True
        para.append(ln)
    words = " ".join(para)
    words = re.sub(r"^[\w./-]+\.(py|js)\s*(--|—|–|-|:)\s*", "", words)
    s = re.match(r"(.+?[.!?])(\s|$)", words)
    return (s.group(1) if s else words).strip()


def _route_body(blk):
    """A route's decorators and its function, up to the next line at the
    left margin that is not part of it."""
    lines = blk.split("\n")
    out, in_def = [], False
    for ln in lines:
        if ln.startswith("def "):
            in_def = True
        elif in_def and ln and not ln[0].isspace() and not ln.startswith("#"):
            break
        out.append(ln)
    return "\n".join(out)


def part_modules():
    """The Connectome: modules as neurons, calls as axons.

    Edges are read, not guessed: a Python `from . import`, a page's call to
    an /api route (to the module the route lives in, or the modules its
    handler in app.py reaches), and a BARRY.name one script defines and
    another uses."""
    files = {}
    for sub, ext in (("backend", ".py"), ("web/js", ".js")):
        root = os.path.join(APP_DIR, *sub.split("/"))
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for fn in fns:
                if not fn.endswith(ext) or fn == "__init__.py":
                    continue
                p = os.path.join(dp, fn)
                rel = os.path.relpath(p, APP_DIR).replace(os.sep, "/")
                try:
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        files[rel] = fh.read()
                except OSError:
                    continue
    py = {rel[len("backend/"):-3].replace("/", "."): rel for rel in files if rel.endswith(".py")}
    edges = Counter()

    # Python -> Python.
    for rel, text in files.items():
        if not rel.endswith(".py"):
            continue
        for mod, names in _PY_FROM_DOT.findall(text):
            targets = [mod] if mod else [n for n, _ in _import_items(names)]
            for t in targets:
                if t in py and py[t] != rel:
                    edges[(rel, py[t])] += 1

    # Routes -> the module that serves them. A route in another module is
    # that module's; a route in app.py goes to the modules its handler
    # reaches, by the names app.py imports them under (and the singletons
    # it builds from them: BANK, REG, CURATE ...).
    app_rel = "backend/app.py"
    app_text = files.get(app_rel, "")
    alias = dict((m, py[m]) for m in py)
    for mod, names in _PY_FROM_DOT.findall(app_text):
        if not mod:
            for name, al in _import_items(names):
                if name in py:
                    alias[al] = py[name]
    for name, mod in re.findall(r"^([A-Z][A-Z_]+)\s*=\s*(\w+)\.[A-Z]\w*\(", app_text, re.M):
        if mod in alias:
            alias[name] = alias[mod]
    routes = []                                          # (path, {module: weight})
    for rel, text in files.items():
        if not rel.endswith(".py"):
            continue
        if rel != app_rel:
            for path in _ROUTE_RE.findall(text):
                routes.append((path, {rel: 1}))
            continue
        for blk in re.split(r"\n(?=@app\.)", text):
            if not blk.startswith("@app."):
                continue
            body = _route_body(blk)
            paths = _ROUTE_RE.findall(body.split("\ndef ", 1)[0])
            if not paths:
                continue
            reach = Counter()
            for word in re.findall(r"\b([A-Za-z_]\w*)\.\w", body):
                if word in alias and alias[word] != app_rel:
                    reach[alias[word]] += 1
            for path in paths:
                routes.append((path, dict(reach) or {app_rel: 1}))
    compiled = [(re.compile("^" + re.sub(r"<[^>]+>", "[^/]+", re.escape(p)) + "$"), p, w)
                for p, w in routes]

    def served_by(path):
        path = path.rstrip("/") or path
        hits = [w for rx, p, w in compiled if rx.match(path)]
        if not hits:
            hits = [w for rx, p, w in compiled if p.startswith(path)]
        return hits[:3]

    for rel, text in files.items():
        if not rel.endswith(".js"):
            continue
        seen = set()
        for path in _API_RE.findall(text):
            path = path.split("?")[0]
            if path in seen or len(path) < 6:
                continue
            seen.add(path)
            for w in served_by(path):
                for mod in w:
                    edges[(rel, mod)] += 1

    # Script -> script, through the BARRY namespace.
    owner = {}
    for rel, text in files.items():
        if rel.endswith(".js"):
            for n in set(_JS_DEF.findall(text)):
                owner.setdefault(n, set()).add(rel)
    for rel, text in files.items():
        if not rel.endswith(".js"):
            continue
        for n in set(_JS_USE.findall(text)):
            own = owner.get(n)
            if own and len(own) == 1 and rel not in own:
                edges[(rel, next(iter(own)))] += 1

    nodes = []
    for rel in sorted(files):
        text = files[rel]
        nodes.append([rel, text.count("\n") + 1, _purpose(rel, text)])
    index = {n[0]: i for i, n in enumerate(nodes)}
    links = [[index[a], index[b], w] for (a, b), w in edges.items() if a in index and b in index]
    return {"cols": ["path", "lines", "purpose"], "nodes": nodes, "links": links,
            "routes": len(routes), "languages": _languages()}


def _languages():
    """Lines of code by language, over the folders a person writes in."""
    lines, files = Counter(), Counter()
    for d in CODE_DIRS:
        for dp, dns, fns in os.walk(os.path.join(APP_DIR, d)):
            dns[:] = [x for x in dns if x not in SKIP_DIRS]
            for fn in fns:
                lang = CODE_EXTS.get(os.path.splitext(fn)[1])
                if not lang:
                    continue
                try:
                    with open(os.path.join(dp, fn), "rb") as fh:
                        n = fh.read().count(b"\n")
                except OSError:
                    continue
                lines[lang] += n
                files[lang] += 1
    return [[k, lines[k], files[k]] for k, _ in lines.most_common()]


# What a set is called, what its last call means, and who made it.
OUTCOME = {"spike": "spike", "ds1": "spike", "ds2": "spike", "solid": "spike",
           "sputter": "spike", "likely_spike": "spike",
           "garbage": "garbage", "likely_garbage": "garbage",
           "flag": "flagged", "review": "flagged"}


def part_calls():
    ai = _hook("ai_labels") or frozenset()
    flows = Counter()
    sets = Counter()
    reviews = Counter()
    for s in _hook("curate").all():
        kind = str(s.get("kind") or "other").split(".")[0]
        if kind not in ("ds", "ied", "pooled"):
            kind = "other"
        sets[kind] += 1
        for e in s.get("events") or []:
            if not isinstance(e, dict):
                continue
            lab = e.get("label")
            if lab == "unspecified":
                lab = None
            if not lab:
                who, out = "nobody", "waiting"
            elif lab in ai:
                who, out = "model", OUTCOME.get(lab, "flagged")
            else:
                who, out = "person", OUTCOME.get(lab, "flagged")
            flows[(kind, who, out)] += 1
            for rv in e.get("reviews") or []:
                by = str((rv or {}).get("by") or "")
                if by and by != "snapshot import":
                    reviews["model" if by.endswith("(AI)") else "person"] += 1
    return {"flows": [[k, w, o, n] for (k, w, o), n in sorted(flows.items())],
            "sets": dict(sets), "reviews": dict(reviews)}


BUILDERS = {"events": part_events, "zoom": part_zoom, "versions": part_versions,
            "modules": part_modules, "calls": part_calls}


# --- totals, worked out from whatever parts are here -------------------------------

def totals(parts):
    t = {}
    ev = parts.get("events")
    if ev:
        t["events"] = sum(r[2] for r in ev["rows"])
        t["entries"] = len(ev["rows"])
        t["bank_versions"] = sum(r[5] for r in ev["rows"])
    z = parts.get("zoom")
    if z:
        rows = z["rows"]
        t["recordings"] = len(rows)
        t["animals"] = len({(r[0], r[1]) for r in rows})
        t["projects"] = len({r[0] for r in rows})
        known = [r for r in rows if r[3] and r[4] and r[5]]
        t["samples"] = int(sum(r[3] * r[4] * r[5] for r in known))
        t["samples_from"] = len(known)
        t["hours"] = round(sum(r[3] for r in rows if r[3]) / 3600.0, 1)
        t["channels"] = int(sum(r[4] for r in rows if r[4]))
    v = parts.get("versions")
    if v:
        t["versions"] = len(v["versions"])
        t["commits"] = sum(v["commits"].values())
        first = min(v["commits"]) if v["commits"] else (v["versions"][0]["day"] if v["versions"] else None)
        if first:
            t["since"] = first
            t["days"] = (date.today() - date.fromisoformat(first)).days + 1
    m = parts.get("modules")
    if m:
        t["lines"] = sum(r[1] for r in m["languages"])
        t["modules"] = len(m["nodes"])
        t["routes"] = m["routes"]
    c = parts.get("calls")
    if c:
        t["calls"] = sum(n for k, w, o, n in c["flows"] if w != "nobody")
        t["sets"] = sum(c["sets"].values())
        t["reviews_people"] = c["reviews"].get("person", 0)
        t["reviews_models"] = c["reviews"].get("model", 0)
    return t


# --- keeping it current ------------------------------------------------------------------

def _load_disk():
    if _STATE["loaded"]:
        return
    _STATE["loaded"] = True
    try:
        with open(CACHE, encoding="utf-8") as fh:
            got = json.load(fh)
        for k in PARTS:
            if k in (got.get("parts") or {}):
                _STATE["parts"][k] = got["parts"][k]
                _STATE["sigs"][k] = (got.get("sigs") or {}).get(k)
    except (OSError, ValueError):
        pass


def _save_disk():
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"parts": _STATE["parts"], "sigs": _STATE["sigs"]}, fh, separators=(",", ":"))
    os.replace(tmp, CACHE)


def _refresh(stale, sigs):
    words = {"events": "the bank", "zoom": "the recordings", "versions": "the patch notes",
             "modules": "the code", "calls": "the curation sets"}
    try:
        for k in stale:
            feed.say("Inside Jarvis: counting %s" % words[k], kind="inside", key="inside-count")
            t0 = time.time()
            try:
                got = BUILDERS[k]()
            except Exception as e:                       # noqa: BLE001
                with _LOCK:
                    _STATE["errors"][k] = str(e)[:300]
                continue
            with _LOCK:
                _STATE["parts"][k] = got
                _STATE["sigs"][k] = sigs[k]
                _STATE["errors"].pop(k, None)
            feed.say("Inside Jarvis: counted %s" % words[k], kind="inside", key="inside-count",
                     ms=(time.time() - t0) * 1000)
        with _LOCK:
            _save_disk()
        feed.say("Inside Jarvis is up to date", kind="inside", key="inside-count", done=True)
    except Exception as e:                               # noqa: BLE001
        feed.say("Inside Jarvis could not count everything: %s" % e, kind="inside",
                 key="inside-count", level="err", done=True)
    finally:
        with _LOCK:
            _STATE["busy"] = False
        _DONE.set()


def census(have=None, wait=0):
    """What the page needs: the parts it does not have at their current
    signature, the signatures, the totals, and whether a recount is on.

    `wait` (seconds) holds the answer until a recount is over. The page never
    asks for it; a harness does, because its clock is not the wall's and a
    poll loop under virtual time is over before the server has counted."""
    have = have or {}
    sigs = signatures()
    with _LOCK:
        _load_disk()
        stale = [k for k in PARTS if _STATE["sigs"].get(k) != sigs[k]]
        if stale and not _STATE["busy"]:
            _STATE["busy"] = True
            _DONE.clear()
            threading.Thread(target=_refresh, args=(stale, sigs), daemon=True,
                             name="jarvis-inside-census").start()
        parts = dict(_STATE["parts"])
        held = dict(_STATE["sigs"])
        busy = _STATE["busy"]
        errors = dict(_STATE["errors"])
    if wait and busy:
        _DONE.wait(wait)
        return census(have)
    send = {k: parts[k] for k in parts if have.get(k) != held.get(k)}
    return {"ok": True, "sigs": held, "parts": send, "totals": totals(parts),
            "busy": busy, "stale": [k for k in stale if k in parts], "missing":
            [k for k in PARTS if k not in parts], "errors": errors,
            "today": date.today().isoformat()}


def install(app, fail, reg=None, bank=None, curate=None, ai_labels=None):
    from flask import jsonify, request
    HOOKS.update(reg=reg, bank=bank, curate=curate, ai_labels=ai_labels)

    @app.route("/api/inside/census")
    def api_inside_census():
        have = {}
        for pair in (request.args.get("have") or "").split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                have[k] = v
        try:
            wait = min(240.0, float(request.args.get("wait") or 0))
            return jsonify(census(have, wait=wait))
        except Exception as e:                           # noqa: BLE001
            return fail("inside.census", e)
