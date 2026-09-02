"""
registry.py -- Walks the repo and builds the script catalog the GUI drives.

Two jobs:
  1. CLASSIFY every .py / .m / .ipynb into a section (IED Pipeline stages, a
     top-level project area, or Misc for anything that fits nowhere).
  2. INTROSPECT each script for a human description and the knobs worth
     exposing -- top-level constants for Python, the function signature for
     MATLAB -- so the Explorer can offer them as form fields.

Nothing here modifies repo files; it only reads them.
"""
from __future__ import annotations

import ast
import os
import re

CODE_EXTS = {".py", ".m", ".ipynb"}

SKIP_DIRS = {
    ".git", ".vs", ".idea", "__pycache__", "node_modules", ".ipynb_checkpoints",
    "venv", ".venv", "env", "dist", "build", "BARRY GUI", ".vscode",
}

# IED stage folders carry their order in the name (01_..10_).
IED_STAGE_RE = re.compile(r"^(\d{2})_(.+)$")

# Areas that are explicitly a scratch/leftover space -> Misc.
MISC_ROOTS = {"Misc", "Playground", "For Rain", "Stats", "3D Plots"}

# Paths that are archived/inactive but still browsable.
ARCHIVE_HINTS = ("_archive", ".Script Archives", ".File Archives", "archive",
                 "Unrelated Code", "Debug")

# Constants that are noise as form fields.
PARAM_SKIP = {"HERE", "__file__", "ROOT", "SCRIPT_DIR"}

PATH_HINT_RE = re.compile(
    r"(path|dir|folder|file|root|out|input|src|dest|csv|xlsx|save)", re.I)


# --------------------------------------------------------------------------
# Scanning
# --------------------------------------------------------------------------
def scan_repo(repo_root):
    """Walk the repo once and return a list of script records."""
    repo_root = os.path.abspath(repo_root)
    items = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in CODE_EXTS:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, repo_root).replace("\\", "/")
            try:
                stat = os.stat(full)
            except OSError:
                continue
            items.append(_make_record(repo_root, rel, full, stat, ext))
    items.sort(key=lambda r: (r["section"], r["stage_order"], r["rel"].lower()))
    return items


def _make_record(repo_root, rel, full, stat, ext):
    parts = rel.split("/")
    top = parts[0] if len(parts) > 1 else "(root)"
    section, stage_order, stage_label = _classify(parts, top, rel)

    lang = {".py": "python", ".m": "matlab", ".ipynb": "notebook"}[ext]
    return {
        "id": rel,
        "rel": rel,
        "name": os.path.basename(rel),
        "dir": "/".join(parts[:-1]) or "(root)",
        "lang": lang,
        "ext": ext,
        "section": section,
        "stage_order": stage_order,
        "stage": stage_label,
        "top": top,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "archived": any(h.lower() in rel.lower() for h in ARCHIVE_HINTS),
        "runnable": lang in ("python", "matlab"),
    }


def _classify(parts, top, rel):
    """Return (section, stage_order, stage_label)."""
    if top == "IED" and len(parts) > 1:
        m = IED_STAGE_RE.match(parts[1])
        if m:
            order = int(m.group(1))
            label = m.group(2).replace("_", " ")
            return "IED Pipeline", order, f"{m.group(1)} {label}"
        return "IED Pipeline", 99, "Support"

    if top == "(root)" or top in MISC_ROOTS:
        return "Misc", 50, top if top != "(root)" else "Loose files"

    return top, 50, parts[1] if len(parts) > 2 else ""


# --------------------------------------------------------------------------
# Introspection
# --------------------------------------------------------------------------
def _read_text(path, limit=400_000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def describe(path, lang):
    """Extract (description, params, extra) for one script."""
    if lang == "python":
        return _describe_python(path)
    if lang == "matlab":
        return _describe_matlab(path)
    if lang == "notebook":
        return _describe_notebook(path)
    return "", [], {}


def _describe_python(path):
    src = _read_text(path)
    if not src:
        return "", [], {}

    desc, params = "", []
    try:
        tree = ast.parse(src)
        doc = ast.get_docstring(tree)
        if doc:
            desc = doc.strip()
        params = _python_params(tree, src)
        extra = {
            "functions": [n.name for n in tree.body
                          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))][:40],
            "imports": sorted(_python_imports(tree))[:40],
            "has_main": "__main__" in src,
        }
    except SyntaxError as exc:
        extra = {"parse_error": f"line {exc.lineno}: {exc.msg}"}

    if not desc:
        desc = _leading_comment(src, "#")
    return desc, params, extra


def _python_imports(tree):
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def _python_params(tree, src):
    """Top-level literal assignments -- the de-facto config block.

    These scripts have no argparse, so their module-level constants ARE the
    interface. We surface literals only; anything computed is left alone.
    """
    lines = src.splitlines()
    params = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        name = targets[0].id
        if name.startswith("_") or name in PARAM_SKIP:
            continue
        value = node.value
        if value is None:
            continue

        kind, literal = _literal_of(value)
        if kind is None:
            continue

        comment = ""
        idx = node.lineno - 1
        if 0 <= idx < len(lines) and "#" in lines[idx]:
            comment = lines[idx].split("#", 1)[1].strip()

        params.append({
            "name": name,
            "type": kind,
            "value": literal,
            "line": node.lineno,
            "comment": comment,
            "is_path": bool(PATH_HINT_RE.search(name)) or
                       (kind == "str" and _looks_like_path(literal)),
        })
    return params[:60]


def _literal_of(node):
    """Return (type_name, python_value) for supported literal nodes."""
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            return "bool", v
        if isinstance(v, (int, float)):
            return "num", v
        if isinstance(v, str):
            return "str", v
        if v is None:
            return "none", None
        return None, None
    if isinstance(node, (ast.List, ast.Tuple)):
        out = []
        for el in node.elts:
            k, v = _literal_of(el)
            if k is None:
                return None, None
            out.append(v)
        return "list", out
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        k, v = _literal_of(node.operand)
        if k == "num":
            return "num", -v if isinstance(node.op, ast.USub) else v
    return None, None


def _looks_like_path(s):
    if not isinstance(s, str) or len(s) < 3:
        return False
    return bool(re.search(r"[\\/]", s)) or bool(re.match(r"^[A-Za-z]:", s)) or \
        bool(re.search(r"\.(csv|xlsx?|mat|png|pdf|svg|json|txt|h5|ncs)$", s, re.I))


def _leading_comment(src, marker):
    """First contiguous comment block at the top of a file."""
    out = []
    for line in src.splitlines():
        s = line.strip()
        if not s:
            if out:
                break
            continue
        if s.startswith(marker):
            text = s.lstrip(marker).strip()
            if text.startswith("!"):        # shebang
                continue
            out.append(text)
        else:
            break
        if len(out) >= 12:
            break
    return "\n".join(out).strip()


MATLAB_FUNC_RE = re.compile(
    r"^\s*function\s+(?:\[(?P<outs>[^\]]*)\]\s*=\s*|(?P<out1>[\w]+)\s*=\s*)?"
    r"(?P<name>[A-Za-z]\w*)\s*(?:\((?P<args>[^)]*)\))?", re.M)


def _describe_matlab(path):
    src = _read_text(path)
    if not src:
        return "", [], {}

    m = MATLAB_FUNC_RE.search(src)
    params, extra = [], {}
    if m:
        args = [a.strip() for a in (m.group("args") or "").split(",") if a.strip()]
        outs = m.group("outs") or m.group("out1") or ""
        extra = {
            "kind": "function",
            "func": m.group("name"),
            "outputs": [o.strip() for o in outs.split(",") if o.strip()],
        }
        for a in args:
            if a == "varargin":
                extra["varargin"] = True
                continue
            params.append({
                "name": a, "type": "str", "value": "", "line": 0, "comment": "",
                "is_path": bool(PATH_HINT_RE.search(a)),
                "required": True,
            })
        # Name/Value options declared via inputParser addParameter.
        for pm in re.finditer(
                r"addParameter\(\s*['\"](\w+)['\"]\s*,\s*([^,)]+)", src):
            params.append({
                "name": pm.group(1), "type": "str",
                "value": pm.group(2).strip().strip("'\""),
                "line": 0, "comment": "optional (Name,Value)",
                "is_path": bool(PATH_HINT_RE.search(pm.group(1))),
                "required": False, "namevalue": True,
            })
    else:
        extra = {"kind": "script"}

    # MATLAB help text: the % block right after the function line.
    body = src[m.end():] if m else src
    desc = _leading_comment(body, "%")
    if not desc:
        desc = _leading_comment(src, "%")
    return desc, params[:60], extra


def _describe_notebook(path):
    import json
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            nb = json.load(fh)
    except Exception as exc:
        return f"(unreadable notebook: {exc})", [], {}

    cells = nb.get("cells", [])
    desc = ""
    for c in cells:
        if c.get("cell_type") == "markdown":
            desc = "".join(c.get("source", []))[:600].strip()
            break
    if not desc:
        for c in cells:
            if c.get("cell_type") == "code":
                desc = _leading_comment("".join(c.get("source", [])), "#")
                if desc:
                    break
    return desc, [], {
        "cells": len(cells),
        "code_cells": sum(1 for c in cells if c.get("cell_type") == "code"),
    }


# --------------------------------------------------------------------------
# Sections summary
# --------------------------------------------------------------------------
def build_sections(items):
    """Group records into sections with counts, for the sidebar."""
    order, groups = [], {}
    for it in items:
        sec = it["section"]
        if sec not in groups:
            groups[sec] = {"name": sec, "count": 0, "python": 0,
                           "matlab": 0, "notebook": 0, "stages": {}}
            order.append(sec)
        g = groups[sec]
        g["count"] += 1
        g[it["lang"]] += 1
        label = it["stage"] or "(other)"
        g["stages"].setdefault(label, {"label": label,
                                       "order": it["stage_order"], "count": 0})
        g["stages"][label]["count"] += 1

    out = []
    for sec in order:
        g = groups[sec]
        g["stages"] = sorted(g["stages"].values(),
                             key=lambda s: (s["order"], s["label"]))
        out.append(g)

    def rank(g):
        if g["name"] == "IED Pipeline":
            return (0, g["name"])
        if g["name"] == "Misc":
            return (2, g["name"])
        return (1, g["name"].lower())

    out.sort(key=rank)
    return out
