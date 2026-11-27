"""Merge the eleven page PDFs into one document (PyMuPDF; run with miniconda's python)."""
import glob
import os

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\DS_Story_Menu_112326"
out = pymupdf.open()
for f in sorted(glob.glob(os.path.join(HERE, "out", "*.pdf"))):
    with pymupdf.open(f) as d:
        out.insert_pdf(d)
out.set_metadata({"title": "Dentate spikes across the mosaic: a menu of stories", "subject": "DS story menu, first round, 2026-11-23",
                  "author": "Barry Lab"})
out.save(os.path.join(DEST, "DS_Story_Menu_112326.pdf"), garbage=3, deflate=True)
print(out.page_count, "pages")
