# -*- coding: utf-8 -*-
"""Any downloaded file -> plain text, so every source can be read and grepped
the same way. Sheets become one block per tab, a row per line, cells joined
by " | " with the cell address of the row's first column, so a fact found in
the text can be pointed back to its cell."""
import csv
import datetime as dt
import io
import os


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d") + ("" if (v.hour, v.minute) == (0, 0) else v.strftime(" %H:%M"))
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, dt.time):
        return v.strftime("%H:%M")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).replace("\n", " / ").strip()


def xlsx_text(path):
    import openpyxl
    out = []
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as e:                               # noqa: BLE001
        return "[unreadable workbook: %s]" % e
    for ws in wb.worksheets:
        out.append("=== TAB: %s" % ws.title)
        for i, row in enumerate(ws.iter_rows(values_only=True), 1):
            cells = [_cell(v) for v in row]
            while cells and not cells[-1]:
                cells.pop()
            if any(cells):
                out.append("R%d: %s" % (i, " | ".join(cells)))
    return "\n".join(out)


def csv_text(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
        rows = list(csv.reader(fh))
    return "\n".join("R%d: %s" % (i, " | ".join(r)) for i, r in enumerate(rows, 1) if any(r))


def docx_text(path):
    import docx
    d = docx.Document(path)
    out = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        out.append("--- table")
        for r in t.rows:
            out.append(" | ".join(c.text.strip().replace("\n", " / ") for c in r.cells))
    return "\n".join(out)


def pdf_text(path):
    import fitz
    out = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, 1):
            t = page.get_text().strip()
            out.append("--- page %d%s" % (i, "" if t else " [no text layer: scanned?]"))
            out.append(t)
    return "\n".join(out)


def to_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        return xlsx_text(path)
    if ext == ".csv":
        return csv_text(path)
    if ext == ".docx":
        return docx_text(path)
    if ext == ".pdf":
        return pdf_text(path)
    if ext in (".txt", ".md", ".m", ".py"):
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    return None
