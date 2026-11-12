# -*- coding: utf-8 -*-
"""The handwritten recording sheets, read by eye in the session that built
Chicken Scratch (2026-11-09), into facts.

Transcriptions live in <work>/hw/hw_*.json, one list per batch: what each
page says, verbatim where it matters, with what looked off in 'flags'.
'src' is the Drive id of the scanned PDF, or '1-pNN' for photo NN of the
'Rec data 072826' folder (in the order of <work>/sheets/index.json).
Writes <work>/facts/handwritten.jsonl.
"""
import glob
import json
import os
import re

W = os.path.expandvars(r"%LOCALAPPDATA%\Jarvis\chickenscratch")


def main():
    src = {s["id"]: s for s in json.load(open(os.path.join(W, "sources.json"), encoding="utf-8"))}
    photos = json.load(open(os.path.join(W, "sheets", "index.json")))
    out = []
    for p in sorted(glob.glob(os.path.join(W, "hw", "hw_*.json"))):
        for e in json.load(open(p, encoding="utf-8")):
            sid = e["src"]
            m = re.fullmatch(r"1-p(\d+)", sid)
            if m:
                path = photos[int(m.group(1))]
                sid = os.path.splitext(os.path.basename(path))[0]
                loc = "photo %s of 'Rec data 072826'" % m.group(1)
            else:
                loc = "page %s" % e.get("page")
            s = src.get(sid) or {}
            out.append({
                "key": e["key"], "project": e["key"].split(":")[0], "raw": e.get("raw") or e["key"].split(":")[1],
                "type": e.get("type") or "recording_session", "date": e.get("date"),
                "date_raw": e.get("date_raw"), "time": None, "who": e.get("who"),
                "session": e.get("session"), "value": e.get("value"), "detail": e.get("detail"),
                "source": "Handwritten notebook: " + (s.get("path") or sid), "source_id": sid,
                "locator": loc, "conf": e.get("conf") or "high", "flags": e.get("flags") or [],
                "origin": "read by eye (Claude, 2026-11-09)"})
    with open(os.path.join(W, "facts", "handwritten.jsonl"), "w", encoding="utf-8") as fh:
        for f in out:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    print("handwritten facts:", len(out))


if __name__ == "__main__":
    main()
