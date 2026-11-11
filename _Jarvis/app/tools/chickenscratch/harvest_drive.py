# -*- coding: utf-8 -*-
"""Download every Drive file that could say something about a mouse, and turn
it into text: sheets, docs, PDFs, text files; photos are only downloaded (they
are read by eye). Writes <work>/drive/<id>.<ext>, <work>/text/<id>.txt and
<work>/sources.json. Read-only against Drive. Safe to re-run: what is already
here is not fetched again."""
import concurrent.futures as cf
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract  # noqa: E402
import gdrive  # noqa: E402

W = os.path.expandvars(r"%LOCALAPPDATA%\Jarvis\chickenscratch")
SKIP_DIRS = ("Helpful Books & Papers", "Papers_Mohsen", "Trainings and certs", "Shopping!",
             "Journal Club", "Past Thesis Defenses", "Events Ranked", "Event Xplorefinder",
             "Average waveform across", "Normalized Raster", "/m22s3jul15")
# Personal or unrelated things shared with the lab account.
SKIP_NAMES = ("GSU Picnic", "Vermont Legislators", "NGP", "Departing Flight", "Operation Candor",
              "Neuro Buddy", "Rain Hours", "Chemical Inventory", "Organizing 431 chemicals",
              "Lab Supplies Tracker", "Ordering info", "Website", "Reading List", "~$")
MAX_BYTES = 40 * 1024 * 1024


def kind(f):
    m, n = f["mimeType"], f["name"].lower()
    if m == "application/vnd.google-apps.spreadsheet" or n.endswith((".xlsx", ".xlsm", ".csv")):
        return "sheet"
    if m == "application/vnd.google-apps.document" or n.endswith(".docx"):
        return "doc"
    if m == "application/vnd.google-apps.presentation" or n.endswith(".pptx"):
        return "slides"
    if m == "application/pdf":
        return "pdf"
    if m in ("image/heif", "image/jpeg") or n.endswith((".heic", ".jpg", ".jpeg")):
        return "photo"
    if m == "text/plain" or n.endswith((".txt", ".md")):
        return "text"
    return None


def wanted(f):
    k = kind(f)
    if not k or f["mimeType"] == "application/vnd.google-apps.folder":
        return None
    p = f.get("path", f["name"])
    if any(s in p for s in SKIP_DIRS) or any(s in f["name"] for s in SKIP_NAMES):
        return None
    if int(f.get("size") or 0) > MAX_BYTES:
        return None
    return k


def one(f, k):
    try:
        local = gdrive.download(f, os.path.join(W, "drive"))
    except Exception as e:                               # noqa: BLE001
        return {"error": "download: %s" % e}
    rec = {"local": local}
    if k != "photo":
        tp = os.path.join(W, "text", f["id"] + ".txt")
        if not os.path.exists(tp):
            try:
                t = extract.to_text(local)
            except Exception as e:                       # noqa: BLE001
                t = "[extract failed: %s]" % e
            if t is not None:
                with open(tp, "w", encoding="utf-8") as fh:
                    fh.write(t)
        if os.path.exists(tp):
            rec["text"] = tp
            rec["chars"] = os.path.getsize(tp)
    return rec


def main():
    os.makedirs(os.path.join(W, "text"), exist_ok=True)
    inv = json.load(open(os.path.join(W, "drive_inventory.json"), encoding="utf-8"))
    todo = [(f, wanted(f)) for f in inv]
    todo = [(f, k) for f, k in todo if k]
    print("files to harvest:", len(todo))
    out = []
    with cf.ThreadPoolExecutor(2) as ex:
        futs = {ex.submit(one, f, k): (f, k) for f, k in todo}
        for i, fu in enumerate(cf.as_completed(futs), 1):
            f, k = futs[fu]
            r = fu.result()
            out.append(dict(id=f["id"], name=f["name"], path=f.get("path"), kind=k,
                            mime=f["mimeType"], modified=f.get("modifiedTime"),
                            created=f.get("createdTime"),
                            owner=(f.get("owners") or [{}])[0].get("emailAddress"),
                            editor=(f.get("lastModifyingUser") or {}).get("displayName"),
                            link=f.get("webViewLink"), **r))
            if i % 50 == 0:
                print(i, "done", flush=True)
    with open(os.path.join(W, "sources.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=0)
    print("errors:", sum(1 for r in out if r.get("error")))
    for r in out:
        if r.get("error"):
            print("  ", r["path"][:100], r["error"][:120])


if __name__ == "__main__":
    main()
