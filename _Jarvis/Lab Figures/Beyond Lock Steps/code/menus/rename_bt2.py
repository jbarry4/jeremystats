import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPL = {
    "pages_b.py": [("DS vs pDS vs IED", "DS vs BT vs IED"),
                   ("STORY 5 · FROM DS TOWARD IED · pDS", "STORY 5 · FROM DS TOWARD IED · BORDERLINE TRANSIENTS"),
                   ("# c: pDS vs IED share", "# c: BT vs IED share"),
                   ("c: pDS and IED-class shares", "c: BT and IED-class shares"),
                   ("than DS. pDS ", "than DS. BTs "),
                   ("# d: per-mouse medians DS -> pDS -> IED", "# d: per-mouse medians DS -> BT -> IED"),
                   ("\"pDS %s). Half-width", "\"BT %s). Half-width")],
    "pages_c.py": [("(\"IED and pDS\",", "(\"IED and BT\",")],
    "m6_package.py": [("# pDS and IED counts", "# BT and IED counts")],
}
for f, pairs in REPL.items():
    p = os.path.join(HERE, f)
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        if a not in s:
            print("NOT FOUND in", f, ":", a)
        s = s.replace(a, b)
    open(p, "w", encoding="utf-8").write(s)
    print(f, "pDS left:", s.count("pDS"))
