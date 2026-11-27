"""Scan the merged Jeremy menu PDF and its tables for words the lab does not use (run with miniconda's python)."""
import glob
import os
import re

import pymupdf

DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\Jeremy_Menu_112426"
BANNED = [r"\bpDS\b", r"A-spike", r"\u2026", r"\.\.\.", r"Twilight", r"survives correction", r"only a lead", r"Bonferroni",
          r"\bFDR\b", r"\bTZ\b", r"P-spike", r"colour", r"optimis", r"centre", r"analys(e|ing)\b"]
doc = pymupdf.open(os.path.join(DEST, "Jeremy_Menu_112426.pdf"))
print(doc.page_count, "pages")
for i, page in enumerate(doc):
    txt = page.get_text()
    for pat in BANNED:
        for m in re.finditer(pat, txt):
            s = txt[max(0, m.start() - 60): m.end() + 40].replace("\n", " ")
            print("page %d  %-22s  %s" % (i + 1, pat, s))
for f in glob.glob(os.path.join(DEST, "tables", "*.csv")):
    t = open(f, encoding="utf-8").read()
    for pat in BANNED:
        n = len(re.findall(pat, t))
        if n:
            print(os.path.basename(f), pat, n)
print("scan done")
