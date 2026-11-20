# -*- coding: utf-8 -*-
"""A first written story for every mouse on the Dentate Spike sheet, made
from its dossier alone: who it is, what was done to it and when, what was
recorded, where it stands in the DS pipeline, what the sources disagree on
and what nobody wrote down.

Deliberately mechanical: every sentence is a fact the dossier holds, with
how many sources back it, so nothing here can be more confident than the
records are. It is the draft a person reads and marks up in Chicken
Scratch; the next pass rewrites it from those marks.

Writes <work>/stories/<key>.json: {summary, timeline, cautions,
open_questions, by, at}.
"""
import collections
import datetime as dt
import json
import os
import re

W = os.path.expandvars(r"%LOCALAPPDATA%\Jarvis\chickenscratch")
OUT = os.path.join(W, "stories")

PROC = [("tail_snip", "tail snip (genotyping)"), ("injection", "injection"),
        ("behavior", "active avoidance / behavior"), ("surgery_headplate", "headplate surgery"),
        ("probe_implant", "probe"), ("surgery_other", "other procedure"),
        ("shipment", "shipment"), ("perfusion", "perfused"), ("death", "ended"),
        ("histology", "histology"), ("brain_bank", "brain bank")]
WORD = dict(PROC)


def d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def nice(s):
    x = d(s)
    return "%d %s %d" % (x.day, x.strftime("%b"), x.year) if x else str(s)


def backing(n):
    return "1 source" if n == 1 else "%d sources" % n


def attr(dz, name):
    a = (dz.get("attrs") or {}).get(name)
    if not a:
        return None, None
    vals = a["values"]
    if a.get("agreed"):
        top = next(v for v in vals if v["value"] == a["agreed"])
        return a["agreed"], len(top["sources"])
    return " or ".join(v["value"] for v in vals[:3]), 0


def sess_num(s):
    m = re.search(r"(\d+)", str(s or ""))
    return str(int(m.group(1))) if m else None


def story(key, dz, facts):
    proj = dz["project"]
    name = key.replace(":", " ")
    parts, cautions, questions, tl = [], [], [], []

    # --- who -------------------------------------------------------------
    sex, ns = attr(dz, "sex")
    dob, nd = attr(dz, "dob")
    who = [name + (" -- " if sex or dob else "")]
    if sex:
        who.append({"M": "male", "F": "female"}.get(sex, sex) +
                   (" (sources disagree)" if ns == 0 else ""))
    if dob:
        who.append(("born %s" % nice(dob)) + (" (sources disagree)" if nd == 0 else ""))
    genes = []
    for g in ("YH", "SST", "PV"):
        v, n = attr(dz, g)
        if v and v not in ("N/A",):
            genes.append("%s %s%s" % (g, v, " (disputed)" if n == 0 else ""))
    if genes:
        who.append(" / ".join(genes))
    cohort, _ = attr(dz, "cohort")
    if cohort:
        who.append(cohort)
    par, _ = attr(dz, "parents")
    sent = ", ".join(x for x in who[1:] if x)
    parts.append(who[0] + sent + "." + (" Parents (SoftMouse): %s." % par if par else ""))

    # PTEN group, from the DS sheet / session inventory
    grp = collections.Counter()
    for f in facts:
        if f["type"] == "group" and f.get("value"):
            grp[re.sub(r"\s+", " ", f["value"])] += 1
    if grp:
        parts.append("Group as the analysis sheets have it: %s." % "; ".join(
            "%s (%s)" % (g, backing(n)) for g, n in grp.most_common(3)))
    virus = sorted({f["value"].split("=", 1)[1] for f in facts if f["type"] == "injection"
                    and f.get("value", "").lower().startswith("virus=")})
    if virus:
        parts.append("Virus: %s." % ", ".join(virus))

    # --- procedures --------------------------------------------------------
    rows = [r for r in dz["timeline"] if r["type"] in WORD]
    proc_lines = []
    for r in rows:
        what = WORD[r["type"]]
        if r["type"] == "probe_implant" and r.get("what") and r["what"] != "probe_implant":
            what = "probe " + r["what"]
        proc_lines.append("%s %s (%s)" % (nice(r["date"]), what, backing(len(r["sources"]))))
        tl.append({"date": r["date"], "what": what, "confidence": backing(len(r["sources"]))})
    if proc_lines:
        parts.append("Procedures on record: " + "; ".join(proc_lines) + ".")
    else:
        questions.append("No dated procedure (tail snip, surgery, probe, perfusion) is on record.")

    # --- recordings -------------------------------------------------------
    recs = collections.OrderedDict()
    for f in sorted((f for f in facts if f["type"] == "recording_session"),
                    key=lambda f: (f.get("date") or "9999", sess_num(f.get("session")) or "")):
        s = sess_num(f.get("session"))
        if not s:
            continue
        r = recs.setdefault(s, {"dates": collections.Counter(), "notes": [], "sources": set()})
        if f.get("date"):
            r["dates"][f["date"]] += 1
        r["sources"].add(f.get("source"))
        det = (f.get("detail") or "").strip()
        if det and "registry" not in (f.get("source") or "") and "Channel Data" not in (f.get("source") or "") \
                and len(r["notes"]) < 3 and not det.startswith("bad channels:"):
            r["notes"].append(det)
    on_sheet = {sess_num(s) for s in (dz.get("focus_sessions") or []) if sess_num(s)}
    rec_lines = []
    for s, r in sorted(recs.items(), key=lambda kv: int(kv[0])):
        dates = [x for x, _ in r["dates"].most_common()]
        when = nice(dates[0]) if dates else "date unknown"
        if len(dates) > 1:
            when += " (also dated %s)" % ", ".join(nice(x) for x in dates[1:3])
        line = "s%s %s%s" % (s, when, " -- on the DS sheet" if s in on_sheet else "")
        rec_lines.append(line)
        tl.append({"date": dates[0] if dates else None, "what": "recording s%s" % s +
                   (" (DS sheet)" if s in on_sheet else ""),
                   "confidence": backing(len(r["sources"]))})
    if rec_lines:
        parts.append("Recordings (%d session numbers): %s." % (len(recs), "; ".join(rec_lines)))

    # What the recording sheets themselves say, session by session: the
    # handwritten pages read by eye and the transcribed Feb-Jun notebook.
    sheet_notes = [f for f in facts if (f.get("source") or "").startswith("Handwritten notebook")
                   or "notebookFeb-Jun" in (f.get("source") or "")]
    sheet_notes.sort(key=lambda f: (f.get("date") or "9999", int(sess_num(f.get("session")) or 0),
                                    f.get("session") or ""))
    lines = []
    for f in sheet_notes:
        if f["type"] not in ("recording_session", "seizure", "note"):
            continue
        s = f.get("session")
        head = "%s%s%s" % (nice(f["date"]) if f.get("date") else "undated",
                           " s%s" % re.sub(r"^[sS]", "", str(s)) if s else "",
                           " [DS sheet]" if sess_num(s) in on_sheet else "")
        body = "; ".join(x for x in (f.get("value"), f.get("detail")) if x)
        lines.append("%s -- %s" % (head, body))
        for fl in f.get("flags") or []:
            cautions.append("%s: %s" % (head, fl))
    if lines:
        parts.append("From the recording sheets, session by session:\n" + "\n".join(lines))
    missing = sorted(on_sheet - set(recs), key=int)
    if missing:
        questions.append("The DS sheet lists session(s) %s, but no recording with that number was "
                         "found in the registry, the notebooks or the folder listings." %
                         ", ".join("s" + m for m in missing))
    if dz.get("focus") and not on_sheet:
        questions.append("On the DS sheet with no session filled in: recorded yet?")

    # notebook / note highlights for the sheet's own sessions
    notes = []
    for f in facts:
        if f["type"] in ("note", "seizure", "health", "exclusion") and f.get("detail"):
            t = f["detail"].strip()
            if 12 < len(t) and t not in notes:
                notes.append(t)
    # --- the DS pipeline --------------------------------------------------
    pipe = [f for f in facts if f["type"] == "analysis" and "DS pipeline" in (f.get("value") or "")]
    for f in pipe:
        det = f.get("detail") or ""
        pairs = [kv.split("=", 1) for kv in det.split("; ") if "=" in kv]
        stage = lambda k: re.search(r"[A-Za-z]{3}", k) and not re.search(
            r"old|prio|docs|error|initial|curator|undecided|#|%", k, re.I)
        done = [k for k, v in pairs if v in ("☑︎", "True", "✅") and stage(k)]
        todo = [k for k, v in pairs if v in ("☐", "False", "⛔") and stage(k)]
        sname = "s%s" % sess_num(f.get("session")) if sess_num(f.get("session")) else "(no session)"
        if done or todo:
            parts.append("DS sheet, %s: done %s; not done %s." % (
                sname, ", ".join(done) or "nothing", ", ".join(todo) or "nothing"))

    # --- end of life -------------------------------------------------------
    end = [r for r in dz["timeline"] if r["type"] in ("perfusion", "death")]
    alive, _ = attr(dz, "alive")
    if not end and alive and "not" in alive:
        questions.append("Marked not alive, but no source dates the end (perfusion, euthanasia or death).")
    if not end and not alive:
        questions.append("No source says whether this mouse is alive or when it ended.")

    # --- disagreements ---------------------------------------------------
    for c in dz.get("conflicts") or []:
        cautions.append(c["text"])
    for f in facts:
        for fl in f.get("flags") or []:
            if "contradict" in fl.lower():
                cautions.append("%s (%s)" % (fl, f.get("source")))

    summary = "\n\n".join(parts)
    if notes:
        summary += "\n\nWhat people wrote about it (first few, verbatim): " + " || ".join(
            n[:400] for n in notes[:4])
    tl.sort(key=lambda x: x["date"] or "9999")
    return {"summary": summary, "timeline": tl, "cautions": cautions[:40],
            "open_questions": questions, "by": "Chicken Scratch draft (automatic, from the dossier)",
            "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}


def main():
    D = json.load(open(os.path.join(W, "dossiers.json"), encoding="utf-8"))
    F = json.load(open(os.path.join(W, "facts_all.json"), encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for key, dz in D.items():
        if not dz.get("focus"):
            continue
        st = story(key, dz, [F[i] for i in dz["facts"] if i in F])
        p = os.path.join(OUT, key.replace(":", "_").replace(" ", "_") + ".json")
        old = None
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                old = json.load(fh)
        if old and not str(old.get("by", "")).startswith("Chicken Scratch draft"):
            continue                    # a hand- or reader-written story stays
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(st, fh, ensure_ascii=False, indent=1)
        n += 1
    print("stories written:", n)


if __name__ == "__main__":
    main()
