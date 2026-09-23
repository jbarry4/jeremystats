# -*- coding: utf-8 -*-
"""Every class the markup applies must resolve to at least one CSS rule.

A class that no rule matches is not a harmless spelling mistake. It is a
control asking to look a certain way and silently not doing it:

    .spinner      X-ray's loading card renders `<div class="spinner">`.
                  The only occurrences of the word in app.css are comments,
                  so the wait shows an empty div.
    .modal-head   five modals in three modules. Twenty-one other modules use
                  `.mh`, which is styled. Those five have naked headers.
    .primary      eleven `btn primary` buttons. `.btn` is already the filled
                  style, so it changes nothing -- but it reads as the
                  counterpart of `btn ghost` and is not one.

None of these fail anything. They all look like ordinary code.

WHAT THIS CANNOT SEE, and why the other check exists. This works one class
at a time, so it only finds a class no selector mentions ANYWHERE.
`.btn.small` is invisible to it: `small` is a real class elsewhere
(`.fb-shots.small`, `.cur-prog.small`), so the token resolves even though
`.btn.small` as a pair matches nothing and those eleven buttons render full
size. Catching that needs the two classes measured together on a real
element, which is what `web/_dev/uiaudit.html` does -- it builds one of each
in the live page and compares. Neither check subsumes the other:

    this one      every class in the source, whether or not it ever renders.
                  Sees modals nobody opened and loading states nobody waited
                  for. Blind to combinations.
    uiaudit       real elements in a real stylesheet, so combinations and
                  unparseable rules both count. Blind to anything not on
                  screen during the run.

    python tools/check_classes.py           report
    python tools/check_classes.py --quiet   exit code only

Exit 1 if anything is unstyled, so it can gate a commit.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
WEB = os.path.join(APP, "web")

# Classes assembled at runtime from a prefix and a value -- `'fold-' + id`,
# `'sb-h-' + n`. The literal prefix is what appears in the source and it is
# not a class anybody applies, so matching it against the stylesheet would
# report a fault that is not there.
PREFIXES = ("fb-", "hk-", "sb-", "sb-h-", "sb-mini-", "fold-", "unfold-")

# Applied by script to mark state, and styled through a parent
# (`.thing.on`, `.row.active`). Present in the stylesheet only in compound
# selectors, which the class scan below does pick up -- these are here for
# the ones that are not styled anywhere at all and legitimately so.
STATE = {"js", "hidden", "on", "off", "active", "now", "done", "sel",
         "none", "dragging", "collapsed"}


def applied():
    """Every class literal the markup applies, with where it came from."""
    out = {}

    def add(name, where):
        if not name or name in STATE or name in PREFIXES:
            return
        # A trailing hyphen is a prefix being concatenated with a value --
        # `'shank-' + n`, `'mode-' + kind`. The literal is never applied on
        # its own, so matching it against the stylesheet reports a fault
        # that is not there.
        if not re.fullmatch(r"[a-z][a-z0-9-]*[a-z0-9]", name):
            return          # a template fragment, not a finished class
        out.setdefault(name, set()).add(where)

    for root, _dirs, files in os.walk(os.path.join(WEB, "js")):
        for fn in sorted(files):
            if not fn.endswith(".js"):
                continue
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8", errors="replace") as fh:
                src = fh.read()
            # `class: 'a b c'` as el() takes it, and classList calls.
            for m in re.finditer(r"class:\s*'([^']*)'", src):
                for c in m.group(1).split():
                    add(c, fn)
            for m in re.finditer(
                    r"classList\.(?:add|remove|toggle)\('([^']*)'", src):
                add(m.group(1), fn)

    for fn in ("index.html",):
        path = os.path.join(WEB, fn)
        with open(path, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        for m in re.finditer(r'class="([^"]*)"', src):
            for c in m.group(1).split():
                add(c, fn)
    return out


def styled():
    """Every class any selector mentions, wherever the rules live.

    Not just app.css. The boot overlay is styled in an inline `<style>` in
    index.html -- it has to be, because it paints before the stylesheet has
    loaded, which is the whole point of it. Reading only the stylesheet
    reported all ten of its classes as unstyled.
    """
    css = ""
    with open(os.path.join(WEB, "app.css"), encoding="utf-8",
              errors="replace") as fh:
        css += fh.read()
    with open(os.path.join(WEB, "index.html"), encoding="utf-8",
              errors="replace") as fh:
        for m in re.finditer(r"<style[^>]*>(.*?)</style>", fh.read(), re.S):
            css += "\n" + m.group(1)
    # Declarations are stripped first, or a value like `#fff` or a font
    # stack would be read as part of a selector.
    css = re.sub(r"\{[^{}]*\}", " ", css)
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    return set(re.findall(r"\.([A-Za-z_][\w-]*)", css))


def main():
    quiet = "--quiet" in sys.argv[1:]
    use, have = applied(), styled()
    dead = sorted((c, sorted(w)) for c, w in use.items() if c not in have)

    if not dead:
        if not quiet:
            print("%d classes applied, every one of them styled."
                  % len(use))
        return 0

    if not quiet:
        print("%d of %d applied classes have no rule in app.css:\n"
              % (len(dead), len(use)))
        for name, where in dead:
            print("  %-22s %s" % ("." + name, " ".join(where)))
        print("\nEach is a control asking to look a certain way and not "
              "doing it.\nGive it the rule it wants, point it at the rule "
              "that already exists,\nor take the class off.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
