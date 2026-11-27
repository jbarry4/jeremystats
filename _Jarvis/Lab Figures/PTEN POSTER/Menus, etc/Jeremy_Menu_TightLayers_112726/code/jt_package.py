"""Tight-layer edition of the Jeremy menu: package the pages, tables and code into Lab Figures (PTEN POSTER/Menus, etc).
Runs j_package.py's own steps with JM_LAYERS=tight, the new folder and outj_tight; then merges the PDF.
  python jt_package.py      (then: miniconda python jt_package.py merge)"""
import os
import sys

os.environ["JM_LAYERS"] = "tight"
HERE = os.path.dirname(os.path.abspath(__file__))
DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\PTEN POSTER\Menus, etc\Jeremy_Menu_TightLayers_112726"
NAME = "Jeremy_Menu_TightLayers_112726"

if sys.argv[1:] == ["merge"]:
    import glob
    import pymupdf
    out = pymupdf.open()
    for f in sorted(glob.glob(os.path.join(HERE, "outj_tight", "*.pdf"))):
        with pymupdf.open(f) as d:
            out.insert_pdf(d)
    out.set_metadata({"title": "Jeremy menu, tight layers", "subject": "2026-11-27", "author": "Barry Lab"})
    out.save(os.path.join(DEST, NAME + ".pdf"), garbage=3, deflate=True)
    print(out.page_count, "pages")
    sys.exit(0)

src = open(os.path.join(HERE, "j_package.py"), encoding="utf-8").read()
old_dest = 'DEST = r"C:\\Users\\Z390\\Desktop\\jeremystats\\_Jarvis\\Lab Figures\\Jeremy_Menu_112426"'
assert old_dest in src, "DEST line"
src = src.replace(old_dest, "DEST = %r" % DEST)
src = src.replace('glob.glob(os.path.join(HERE, "outj", "*.*"))', 'glob.glob(os.path.join(HERE, "outj_tight", "*.*"))')
src = src.replace('"j_check_und2.py", "jfollow.py")', '"j_check_und2.py", "jfollow.py", "jtight_supp.py", "jt_package.py",\n'
                  '          "tight_layers.py", "tight_layers.json", "layer_check.py")')
g = {"__name__": "__main__", "__file__": os.path.join(HERE, "j_package.py")}
exec(compile(src, "j_package.py (tight)", "exec"), g)
