# -*- coding: utf-8 -*-
"""Parse every piece of JavaScript in the app and say which ones do not.

This exists because of the way a broken script fails here. There is no
bundler and no build step -- `index.html` loads each file with a plain
`<script src>` -- so a syntax error is not a red line in a terminal, it is
one module quietly never assigning itself. `BARRY.views.sessions` becomes
`undefined`, the view renders nothing, and every OTHER view still works, so
the app looks fine unless you happen to open the one that broke.

It cost twice in one afternoon. A `const reg` shadowing another `reg` took
the whole Sessions module out; a `const before` in a harness page meant that
page ran none of its checks and reported "0 ok, 0 fail", which reads exactly
like a page that has no checks by design.

`node --check` answers in milliseconds and needs nothing installed beyond
node, which is already here.

    python tools/check_js.py          every module and every harness page
    python tools/check_js.py web/js   just those

Reads only. Writes nothing, starts no server, touches no data.
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def node_ok(source, label):
    """(ok, message) for one blob of JavaScript."""
    tmp = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                      encoding="utf-8")
    try:
        tmp.write(source)
        tmp.close()
        p = subprocess.run(["node", "--check", tmp.name],
                           capture_output=True, text=True)
        if p.returncode == 0:
            return True, ""
        # node names the temp file; say the real one instead.
        msg = (p.stderr or "").replace(tmp.name, label)
        # The first line that looks like the error, plus the caret line above
        # it, is the whole useful part.
        lines = [l for l in msg.splitlines() if l.strip()]
        keep = []
        for l in lines:
            keep.append(l)
            if "Error" in l:
                break
        return False, "\n      ".join(keep[:6])
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def inline_scripts(path):
    """Every inline <script> body in an HTML file, with its line offset."""
    text = open(path, encoding="utf-8", errors="replace").read()
    out = []
    for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                         text, re.S):
        # Keep the line numbering honest: pad with the newlines that came
        # before it, so node's "line 166" is the line in the HTML file.
        before = text[:m.start(1)].count("\n")
        out.append("\n" * before + m.group(1))
    return out


def main():
    where = sys.argv[1:] or ["web/js", "web/_dev"]
    files = []
    for w in where:
        base = os.path.join(ROOT, w.replace("/", os.sep))
        if os.path.isfile(base):
            files.append(base)
            continue
        for dirpath, _dirs, names in os.walk(base):
            for n in sorted(names):
                if n.endswith(".js") or n.endswith(".html"):
                    files.append(os.path.join(dirpath, n))

    if not files:
        print("Nothing to check in: " + ", ".join(where))
        return 1

    try:
        subprocess.run(["node", "--version"], capture_output=True)
    except FileNotFoundError:
        print("node is not on PATH, so nothing can be parsed. Install node, "
              "or run the harness suite instead.")
        return 1

    bad = []
    n_js = n_inline = 0
    for path in files:
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        if path.endswith(".js"):
            n_js += 1
            ok, msg = node_ok(
                open(path, encoding="utf-8", errors="replace").read(), rel)
            if not ok:
                bad.append((rel, msg))
        else:
            for i, body in enumerate(inline_scripts(path)):
                n_inline += 1
                label = rel if i == 0 else "%s (script %d)" % (rel, i + 1)
                ok, msg = node_ok(body, label)
                if not ok:
                    bad.append((label, msg))

    print("%d module(s) and %d inline script(s) parsed" % (n_js, n_inline))
    if not bad:
        print("all of them parse.")
        return 0
    print("")
    for rel, msg in bad:
        print("  FAIL  %s" % rel)
        print("      %s" % msg)
    print("")
    print("%d of %d do not parse." % (len(bad), n_js + n_inline))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
