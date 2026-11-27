"""Merge the Jeremy menu's page PDFs into one document (PyMuPDF; run with miniconda's python)."""
import glob
import os

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\Jeremy_Menu_112426"
out = pymupdf.open()
for f in sorted(glob.glob(os.path.join(HERE, "outj", "*.pdf"))):
    with pymupdf.open(f) as d:
        out.insert_pdf(d)
out.set_metadata({"title": "Jeremy menu: Jeremy's questions, answered from the dentate spike data", "subject": "2026-11-24",
                  "author": "Barry Lab"})
out.save(os.path.join(DEST, "Jeremy_Menu_112426.pdf"), garbage=3, deflate=True)
print(out.page_count, "pages")
