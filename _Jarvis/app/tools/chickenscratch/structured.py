# -*- coding: utf-8 -*-
"""Facts from the sources that already have columns: the Lab Operations
Schedule's tabs, the PTEN/KCNT1 Dentate Spike Data sheet, Jarvis's registry
and mouse book, SoftMouse, VOS. No reading between the lines here -- every
fact is one cell (or one record) and says which.

A fact is one line of <work>/facts/structured.jsonl:
  key       "KCNT1:1619" / "PTEN:m13" -- the mouse as Chicken Scratch files it
  project   KCNT1 | PTEN | DEWEY | other
  raw       the mouse as the source wrote it
  type      see TYPES
  date      YYYY-MM-DD (or YYYY-MM, or null); date_raw as written
  time, who, session, value, detail
  source    short name; source_id (Drive id / local path); locator (tab!cell)
  conf      high | medium | low
  origin    "structured"
"""
import datetime as dt
import json
import os
import re

import openpyxl
from openpyxl.utils import get_column_letter

W = os.path.expandvars(r"%LOCALAPPDATA%\Jarvis\chickenscratch")
LABOPS = "1SDXG1GpRhkjq2aKri3n06nOuR8TGio9QuQsyN656ERo"
DSDATA = "1fOQ9Vd2GXCJzEmngs1-wyvbL5xfUdCDciF69s3_IBv8"

TYPES = ("identity", "sex", "dob", "genotype", "group", "cage", "parents", "role", "alive",
         "tail_snip", "injection", "behavior", "surgery_headplate", "probe_implant",
         "surgery_other", "recording_session", "drug", "seizure", "health", "death",
         "perfusion", "histology", "brain_bank", "calendar", "analysis", "exclusion", "note",
         "census", "shipment")

OUT = []


def iso(v):
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    return None


def txt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (dt.datetime, dt.date)):
        return iso(v)
    return str(v).strip()


def kcnt1_key(raw):
    s = txt(raw)
    m = re.fullmatch(r"[Mm]?-?0*(\d{2,5})", s.replace(" ", ""))
    return ("KCNT1:" + m.group(1)) if m else None


def pten_key(raw):
    s = txt(raw).lower().replace(" ", "")
    m = re.fullmatch(r"m?0*(\d{1,3})", s)
    return ("PTEN:m" + m.group(1)) if m else None


def fact(key, project, raw, type_, source, source_id, locator, date=None, date_raw=None,
         value=None, detail=None, who=None, time=None, session=None, conf="high"):
    if not key:
        return
    OUT.append({"key": key, "project": project, "raw": txt(raw), "type": type_,
                "date": date, "date_raw": date_raw, "time": time, "who": who,
                "session": session, "value": value, "detail": detail, "source": source,
                "source_id": source_id, "locator": locator, "conf": conf,
                "origin": "structured"})


# --- the Lab Operations Schedule ------------------------------------------------

EVENT_TYPES = [
    (r"^tail snip", "tail_snip"), (r"^inject", "injection"), (r"^active avoidance", "behavior"),
    (r"^headplate", "surgery_headplate"), (r"^h(3|10)", "probe_implant"),
    (r"^perfuse", "perfusion"), (r"^euthanize", "death"),
    (r"^(slice|stain|image|hippocampus sectioning|m2 sectioning|sliced|stained|imaged)",
     "histology"),
    (r"^(skull thinning|ultrasound|opto|headplated|injected|h3 probe|h10 probe)", None),
]
ATTR_TYPES = {"sex": "sex", "yh": "genotype", "sst": "genotype", "pv": "genotype",
              "role": "role", "alive": "alive", "dob": "dob", "cage id": "cage",
              "notes": "note", "brain bank": "brain_bank", "location": "brain_bank",
              "status": "brain_bank", "sectioning notes": "histology",
              "initial # of slides": "histology", "current # slides": "histology",
              "current slide #": "histology"}
COMPANIONS = ("time", "lead", "sessions", "delayed?", "double inj?")


def ev_type(h):
    hl = h.lower().strip()
    for pat, t in EVENT_TYPES:
        if re.search(pat, hl):
            return t or ("surgery_other" if not hl.startswith(("h3", "h10", "opto")) else
                         "probe_implant")
    return None


def labops_tracker(ws, source, sid, id_col_names=("mouse id", "f", "mouse")):
    hdr = [txt(c.value) for c in ws[1]]
    idc = next((i for i, h in enumerate(hdr) if h.lower() in id_col_names), 0)
    for row in ws.iter_rows(min_row=2):
        raw = row[idc].value if idc < len(row) else None
        key = kcnt1_key(raw)
        if not key:
            continue
        rnum = row[0].row
        loc = lambda j: "%s!%s%d" % (ws.title, get_column_letter(j + 1), rnum)
        j = 0
        while j < len(hdr):
            h = hdr[j]
            hl = h.lower()
            cell = row[j] if j < len(row) else None
            v = cell.value if cell is not None else None
            if cell is not None and cell.comment:
                body = re.sub(r"(?s)^\[Threaded comment\].*?Comment:\s*", "", cell.comment.text).strip()
                body = re.sub(r"\s*\n\s*", " / ", body)
                fact(key, "KCNT1", raw, "note", source, sid, loc(j),
                     value="cell note on %s" % h, detail=body, conf="medium")
            t = ev_type(h) if h else None
            if t and hl not in COMPANIONS:
                comp = {}
                k = j + 1
                while k < len(hdr) and hdr[k].lower() in COMPANIONS:
                    comp[hdr[k].lower()] = row[k].value if k < len(row) else None
                    k += 1
                if v not in (None, "", False):
                    who = txt(comp.get("lead"))
                    fact(key, "KCNT1", raw, t, source, sid, loc(j), date=iso(v),
                         date_raw=txt(v), value=h,
                         detail="; ".join("%s: %s" % (a, txt(b)) for a, b in comp.items()
                                          if txt(b) and a != "lead") or None,
                         who=who if who and who != "UNDOCUMENTED" else None,
                         time=txt(comp.get("time")) or None,
                         session=txt(comp.get("sessions")) or None,
                         conf="high" if iso(v) else "medium")
                j = k
                continue
            at = ATTR_TYPES.get(hl)
            if at and v not in (None, "", False):
                fact(key, "KCNT1", raw, at, source, sid, loc(j), date=iso(v) if at == "dob" else None,
                     date_raw=txt(v) if at == "dob" else None, value=("%s=%s" % (h, txt(v)))
                     if at == "genotype" else txt(v))
            elif hl == "script sync data" and v:
                try:
                    cal = json.loads(v)
                except ValueError:
                    cal = {}
                for what, e in cal.items():
                    s = e.get("s")
                    when = dt.datetime.fromtimestamp(s / 1000) if s else None
                    fact(key, "KCNT1", raw, "calendar", "Lab calendar (via sheet sync)", sid,
                         loc(j), date=when.date().isoformat() if when else None,
                         time=when.strftime("%H:%M") if when else None, value=what,
                         detail=e.get("t"), conf="medium")
            j += 1


def labops_simple(ws, source, sid, id_col, type_map):
    """A tab of one mouse per row with plain columns."""
    hdr = [txt(c.value) for c in ws[1]]
    for row in ws.iter_rows(min_row=2):
        raw = row[id_col].value if id_col < len(row) else None
        key = kcnt1_key(raw)
        if not key:
            continue
        for j, h in enumerate(hdr):
            if j == id_col or j >= len(row):
                continue
            v = row[j].value
            if v in (None, "", False):
                continue
            t = type_map(h)
            if not t:
                continue
            fact(key, "KCNT1", raw, t, source, sid, "%s!%s%d" % (ws.title, get_column_letter(j + 1),
                                                                 row[0].row),
                 date=iso(v), date_raw=txt(v), value=h if iso(v) else "%s=%s" % (h, txt(v)),
                 conf="medium")


def labops_rows(ws, source, sid, id_col, type_, date_col=None, who_col=None, sess_col=None,
                proj="KCNT1"):
    """A log tab: one event per row; the whole row kept as detail."""
    hdr = [txt(c.value) for c in ws[1]]
    for row in ws.iter_rows(min_row=2, values_only=True):
        raw = row[id_col] if id_col < len(row) else None
        key = kcnt1_key(raw)
        if not key:
            continue
        d = row[date_col] if date_col is not None else None
        fact(key, proj, raw, type_, source, sid, "%s!row" % ws.title,
             date=iso(d), date_raw=txt(d) or None,
             who=txt(row[who_col]) if who_col is not None else None,
             session=txt(row[sess_col]) if sess_col is not None else None,
             detail=" | ".join("%s: %s" % (h, txt(v)) for h, v in zip(hdr, row) if txt(v)),
             conf="medium")


def labops():
    p = os.path.join(W, "drive", LABOPS + ".xlsx")
    wb = openpyxl.load_workbook(p, data_only=True)
    src = "Lab Operations Schedule"
    labops_tracker(wb["KCNT1 Active 2.0"], src + " / KCNT1 Active 2.0", LABOPS)
    labops_tracker(wb["KCNT1 Active (Archived)"], src + " / KCNT1 Active (Archived v1)", LABOPS)
    labops_tracker(wb["Sanity Check"], src + " / Sanity Check (older)", LABOPS)

    def arch(h):
        hl = h.lower()
        if hl in ("sex",):
            return "sex"
        if hl in ("yh", "sst", "pv"):
            return "genotype"
        if hl == "dob":
            return "dob"
        if hl == "alive":
            return "alive"
        if hl == "notes":
            return "note"
        if hl.startswith("tail snip"):
            return "tail_snip"
        if hl == "active avoidance":
            return "behavior"
        if hl == "headplated":
            return "surgery_headplate"
        if hl == "injected":
            return "injection"
        if hl in ("h3 probe", "h10 probe", "opto"):
            return "probe_implant"
        if hl.startswith("perfused"):
            return "perfusion"
        if hl in ("sliced", "stained", "imaged"):
            return "histology"
        if hl in ("skull thinning", "ultrasound"):
            return "surgery_other"
        if hl in ("dylan thesis?", "sample available?", "well plate #"):
            return "note"
        return None
    labops_simple(wb["KCNT1 Archive"], src + " / KCNT1 Archive", LABOPS, 2, arch)
    labops_rows(wb["Lab Notebook Import"], src + " / Lab Notebook Import", LABOPS, 3,
                "recording_session", date_col=2, who_col=5, sess_col=4)
    labops_rows(wb["Recording Binder Import"], src + " / Recording Binder Import", LABOPS, 2,
                "recording_session", date_col=0, who_col=6, sess_col=4)
    labops_rows(wb["Comment Import Report"], src + " / Comment Import Report", LABOPS, 1, "note")
    labops_rows(wb["Notes Sanity Check"], src + " / Notes Sanity Check", LABOPS, 0, "note")
    labops_rows(wb["KCNT1_recording_#s"], src + " / KCNT1_recording_#s", LABOPS, 0, "note")
    labops_rows(wb["Migration Sanity Check"], src + " / Migration Sanity Check", LABOPS, 1, "note")
    labops_rows(wb["Lab Notebook Report"], src + " / Lab Notebook Report", LABOPS, 1, "note")
    labops_rows(wb["Recording Import Report"], src + " / Recording Import Report", LABOPS, 1, "note")


# --- the Dentate Spike Data sheet (the focus list) -------------------------------

def dsdata():
    p = os.path.join(W, "drive", DSDATA + ".xlsx")
    wb = openpyxl.load_workbook(p, data_only=True)
    src = "PTEN/KCNT1 Dentate Spike Data"
    focus = {}
    ws = wb["KCNT1 Recording Sessions"]
    hdr = [txt(c.value) for c in ws[1]]
    for row in ws.iter_rows(min_row=2):
        raw = row[0].value
        key = kcnt1_key(raw)
        if not key:
            continue
        sess = txt(row[1].value) or None
        cells = {hdr[j] + ("#%d" % j if hdr[j] in ("Curator", "▲#", "🗑️#", "🏳️‍🌈#") else ""):
                 txt(c.value) for j, c in enumerate(row) if j < len(hdr)}
        focus.setdefault(key, {"project": "KCNT1", "raw": txt(raw), "sessions": [], "rows": []})
        focus[key]["rows"].append(row[0].row)
        if sess:
            focus[key]["sessions"].append(sess)
        loc = "KCNT1 Recording Sessions!A%d" % row[0].row
        for h in ("Sex", "YH", "SST", "PV"):
            j = hdr.index(h)
            if txt(row[j].value):
                fact(key, "KCNT1", raw, "sex" if h == "Sex" else "genotype", src, DSDATA, loc,
                     value=txt(row[j].value) if h == "Sex" else "%s=%s" % (h, txt(row[j].value)))
        notes = txt(row[hdr.index("Notes")].value)
        if notes:
            fact(key, "KCNT1", raw, "note", src, DSDATA, loc, session=sess, value="DS sheet note",
                 detail=notes)
        status = {k: v for k, v in cells.items() if v and k not in ("Mouse ID", "Session", "Sex",
                                                                      "YH", "SST", "PV", "Notes")}
        fact(key, "KCNT1", raw, "analysis", src, DSDATA, loc, session=sess,
             value="DS pipeline status" + (" (no session listed)" if not sess else ""),
             detail="; ".join("%s=%s" % kv for kv in status.items()))
    for tab, hits in (("PTEN Recording Sessions_Hits", True), ("PTEN Recording Sessions_Misses", False)):
        ws = wb[tab]
        hdr = [txt(c.value) for c in ws[1]]
        for row in ws.iter_rows(min_row=2):
            raw = row[0].value
            key = pten_key(raw)
            if not key:
                continue
            g = lambda name: txt(row[hdr.index(name)].value) if name in hdr else ""
            sess = g("session") or None
            focus.setdefault(key, {"project": "PTEN", "raw": txt(raw), "sessions": [], "rows": []})
            focus[key]["sessions"].append(sess)
            focus[key]["rows"].append("%s:%d" % (tab, row[0].row))
            loc = "%s!A%d" % (tab, row[0].row)
            fact(key, "PTEN", raw, "group", src, DSDATA, loc, session=sess,
                 value="grp=%s subgrp=%s" % (g("grp") or g("group"), g("subgrp")))
            fact(key, "PTEN", raw, "recording_session", src, DSDATA, loc, session=sess,
                 value="session %s, condition %s (%s list)" % (sess, g("cond."),
                                                              "Hits" if hits else "Misses"),
                 detail="bad channels: %s" % g("bad_chan."))
            for n in ("New Notes", "Archive Notes", "Check CSDs"):
                if g(n):
                    fact(key, "PTEN", raw, "note", src, DSDATA, loc, session=sess, value=n,
                         detail=g(n))
            status = {h: txt(c.value) for h, c in zip(hdr, row) if txt(c.value) and h not in
                      ("🐭ID", "session", "New Notes", "Archive Notes", "Check CSDs")}
            fact(key, "PTEN", raw, "analysis", src, DSDATA, loc, session=sess,
                 value="DS pipeline status (%s)" % ("Hits" if hits else "Misses"),
                 detail="; ".join("%s=%s" % kv for kv in status.items()))
    ws = wb["Channel Data"]
    hdr = [txt(c.value) for c in ws[1]]
    seen = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        key = pten_key(row[0])
        if not key:
            continue
        sig = (key, txt(row[2]), txt(row[3]), txt(row[4]), txt(row[5]))
        if sig in seen:
            continue
        seen.add(sig)
        fact(key, "PTEN", row[0], "recording_session", src + " / Channel Data", DSDATA,
             "Channel Data", session=txt(row[2]),
             value="session %s cond %s grp %s" % (txt(row[2]), txt(row[4]), txt(row[5])),
             detail="folder: %s" % txt(row[3]), conf="medium")
    with open(os.path.join(W, "focus.json"), "w", encoding="utf-8") as fh:
        json.dump(focus, fh, indent=1)
    return focus


# --- Jarvis, SoftMouse, VOS -----------------------------------------------------

def jarvis():
    for r in json.load(open(os.path.join(W, "registry.json"), encoding="utf-8")):
        proj = r.get("project") or ""
        if proj.startswith("KCNT1"):
            key, p = kcnt1_key(r.get("mouse")), "KCNT1"
        elif proj == "PTEN":
            key, p = pten_key(r.get("mouse")), "PTEN"
        else:
            continue
        here = r.get("here") or r.get("paths") or []
        start = r.get("start") or ""
        local = None
        if start:
            try:
                local = dt.datetime.fromisoformat(start).astimezone()
            except ValueError:
                local = None
        fact(key, p, r.get("mouse"), "recording_session", "Jarvis registry (%s)" % proj,
             "registry:" + r.get("gid", ""), r.get("gid"),
             date=local.date().isoformat() if local else None,
             time=local.strftime("%H:%M") if local else None, session=txt(r.get("session")),
             value="recording %s%s" % (r.get("label") or "", " [retired]" if r.get("retired") else ""),
             detail="folders: " + "; ".join(str(h) for h in here[:4]),
             conf="high")
    for m in json.load(open(os.path.join(W, "mice.json"), encoding="utf-8")):
        proj = m.get("project") or ""
        key = kcnt1_key(m.get("mouse")) if proj.startswith("KCNT1") else (
            pten_key(m.get("mouse")) if proj == "PTEN" else None)
        for a, v in (m.get("attrs") or {}).items():
            t = {"dob": "dob", "sex": "sex", "genotype": "genotype", "cage": "cage",
                 "group": "group", "subgroup": "group", "implant": "probe_implant",
                 "status": "alive", "role": "role"}.get(a, "note")
            fact(key, proj.split()[0] if proj else "", m.get("mouse"), t,
                 "Jarvis mouse book", "mice:%s/%s" % (proj, m.get("mouse")), a,
                 value="%s=%s" % (a, v), conf="medium")


def softmouse():
    for m in json.load(open(os.path.join(W, "softmouse.json"), encoding="utf-8")):
        tag = re.sub(r"<[^>]+>", "", str(m.get("physicaltag") or "")).strip()
        key = kcnt1_key(tag)
        src, sid = "SoftMouse.NET (live list, 2026-11-07)", "softmouse:%s" % m.get("id")

        def f(t, value, date=None, detail=None):
            fact(key, "KCNT1", tag, t, src, sid, "mouse %s" % m.get("id"), date=date,
                 date_raw=date, value=value, detail=detail)
        clean = lambda k: re.sub(r"<[^>]+>", " ", str(m.get(k) or "")).strip()
        if clean("sex"):
            f("sex", clean("sex"))
        if clean("dateofbirth"):
            f("dob", clean("dateofbirth"), date=_us_date(clean("dateofbirth")))
        if clean("genotype"):
            f("genotype", clean("genotype"))
        if clean("mousestate"):
            f("role", clean("mousestate"))
        if clean("cagetag"):
            f("cage", "SoftMouse cage " + clean("cagetag"))
        if clean("ftag") or clean("mtag"):
            f("parents", "sire %s, dam %s" % (clean("ftag") or "?", clean("mtag") or "?"))
        if clean("mouseline"):
            f("identity", "line " + clean("mouseline"))
        if clean("enddate"):
            f("death", clean("endtype") or "ended", date=_us_date(clean("enddate")),
              detail=clean("endreason") or None)
        if clean("comment"):
            f("note", "SoftMouse comment", detail=clean("comment"))


def _us_date(s):
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def vos():
    for rec in json.load(open(os.path.join(W, "vos.json"), encoding="utf-8")):
        for row in rec.get("census") or []:
            mid, cage, dob, sex = (row + [None] * 5)[:4]
            key = kcnt1_key(mid)
            fact(key, "KCNT1", mid, "census", "VOS census %s" % rec.get("date"),
                 "vos:" + rec.get("file", ""), rec.get("file"), date=rec.get("date"),
                 value="on a VOS cage card: cage %s" % cage,
                 detail="card DOB %s, sex %s%s" % (dob, sex, (", strain %s" % row[4]) if len(row) > 4 and row[4] else ""))


if __name__ == "__main__":
    os.makedirs(os.path.join(W, "facts"), exist_ok=True)
    labops()
    n1 = len(OUT)
    focus = dsdata()
    jarvis()
    softmouse()
    vos()
    with open(os.path.join(W, "facts", "structured.jsonl"), "w", encoding="utf-8") as fh:
        for f in OUT:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    from collections import Counter
    print("facts:", len(OUT), "(lab ops %d)" % n1)
    print(Counter(f["type"] for f in OUT).most_common())
    print("focus mice:", len(focus), Counter(v["project"] for v in focus.values()))
