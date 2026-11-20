"""
chickenscratch.py -- Chicken Scratch (BETA): everything the lab ever wrote
about each PTEN and KCNT1 mouse, in one place, with the disagreements left
showing.

The facts are gathered by tools/chickenscratch/ (the Drive, this repo,
Jarvis's registry and mouse book, SoftMouse, VOS, the Lab Operations
Schedule, handwritten notebooks read by eye) into a work folder that stays
on this machine: %LOCALAPPDATA%\\Jarvis\\chickenscratch. Not the repo, which
is public, and some of what is read comes from the Drive's Non-Public folders.

This module only serves that folder to web/chickenscratch.html and keeps
what people say back about it:

    GET  /api/chickenscratch/index          every mouse, focus first
    GET  /api/chickenscratch/mouse?key=     one dossier, its facts, its story
    GET  /api/chickenscratch/notes          every note left so far
    POST /api/chickenscratch/note           {key, verdict, text, fact?, conflict?}
    GET  /api/chickenscratch/image?path=    a scanned page or photo a fact cites

Notes are appended to notes.jsonl in the work folder, never rewritten, so
a later pass can read exactly what was said and when.
"""
from __future__ import annotations

import json
import os
import threading
import time

from flask import jsonify, request, send_file

W = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                 "Jarvis", "chickenscratch")
NOTES = os.path.join(W, "notes.jsonl")
STORIES = os.path.join(W, "stories")
VERDICTS = ("confirm", "wrong", "unsure", "note")

_CACHE = {"stamp": None, "dossiers": None, "facts": None, "sources": None}
_LOCK = threading.Lock()
WHO = {"fn": None}


def _load():
    paths = [os.path.join(W, n) for n in ("dossiers.json", "facts_all.json")]
    try:
        stamp = tuple(os.path.getmtime(p) for p in paths)
    except OSError:
        return None
    with _LOCK:
        if _CACHE["stamp"] != stamp:
            with open(paths[0], encoding="utf-8") as fh:
                dossiers = json.load(fh)
            with open(paths[1], encoding="utf-8") as fh:
                facts = json.load(fh)
            links = {}
            for name in ("sources.json", "local_sources.json"):
                try:
                    with open(os.path.join(W, name), encoding="utf-8") as fh:
                        for s in json.load(fh):
                            links[s["id"]] = {"link": s.get("link"), "path": s.get("path"),
                                              "scan_pages": s.get("scan_pages"),
                                              "photo": s.get("photo")}
                except OSError:
                    pass
            _CACHE.update(stamp=stamp, dossiers=dossiers, facts=facts, sources=links)
    return _CACHE


def _notes(key=None):
    out = []
    try:
        with open(NOTES, encoding="utf-8") as fh:
            for line in fh:
                try:
                    n = json.loads(line)
                except ValueError:
                    continue
                if key is None or n.get("key") == key:
                    out.append(n)
    except OSError:
        pass
    return out


def _story(key):
    p = os.path.join(STORIES, key.replace(":", "_").replace(" ", "_") + ".json")
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _summary(d, notes_by):
    a = d.get("attrs") or {}
    pick = lambda name: (a.get(name) or {}).get("agreed") or (
        ((a.get(name) or {}).get("values") or [{}])[0].get("value"))
    genes = " ".join("%s %s" % (g, pick(g)) for g in ("YH", "SST", "PV") if pick(g)
                     and pick(g) not in ("N/A",))
    last = next((r for r in reversed(d.get("timeline") or [])
                 if r["type"] not in ("census", "calendar")), None)
    return {"key": d["key"], "project": d["project"], "focus": d.get("focus"),
            "cohort": pick("cohort"), "sex": pick("sex"), "dob": pick("dob"),
            "genes": genes, "alive": pick("alive"), "n_facts": d.get("n_facts"),
            "n_conflicts": len(d.get("conflicts") or []), "n_notes": notes_by.get(d["key"], 0),
            "story": os.path.exists(os.path.join(STORIES, d["key"].replace(":", "_").replace(" ", "_") + ".json")),
            "last": last and {"date": last["date"], "type": last["type"]}}


def index():
    c = _load()
    if not c:
        return {"ok": True, "ready": False, "mice": []}
    notes_by = {}
    for n in _notes():
        notes_by[n.get("key")] = notes_by.get(n.get("key"), 0) + 1
    mice = [_summary(d, notes_by) for d in c["dossiers"].values()]
    mice.sort(key=lambda m: (not m["focus"], m["project"], _num(m["key"])))
    built = max(c["stamp"])
    return {"ok": True, "ready": True, "built": built, "mice": mice,
            "n_facts": len(c["facts"]), "n_sources": len({f.get("source") for f in c["facts"].values()})}


def _num(key):
    import re
    m = re.search(r"(\d+)", key.split(":", 1)[-1])
    return (int(m.group(1)) if m else 10 ** 9, key)


def mouse(key):
    c = _load()
    if not c or key not in c["dossiers"]:
        return None
    d = c["dossiers"][key]
    facts = [c["facts"][i] for i in d["facts"] if i in c["facts"]]
    for f in facts:
        s = c["sources"].get(f.get("source_id")) or {}
        f["link"] = s.get("link")
        imgs = s.get("scan_pages") or ([s["photo"]] if s.get("photo") else [])
        if imgs:
            f["images"] = imgs
    return {"ok": True, "dossier": d, "facts": facts, "story": _story(key),
            "notes": _notes(key)}


def add_note(body):
    key = str(body.get("key") or "").strip()
    verdict = body.get("verdict") or "note"
    text = str(body.get("text") or "").strip()
    if not key or verdict not in VERDICTS or (verdict == "note" and not text):
        raise ValueError("a note needs a mouse, a verdict (%s) and, for a plain note, words"
                         % ", ".join(VERDICTS))
    person, machine = (WHO["fn"] or (lambda: (None, None)))()
    n = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "key": key, "verdict": verdict,
         "text": text, "fact": body.get("fact"), "conflict": body.get("conflict"),
         "attr": body.get("attr"), "choice": body.get("choice"), "via": body.get("via"),
         "by": person, "machine": machine}
    os.makedirs(W, exist_ok=True)
    with open(NOTES, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    return n


# --- the Quest: one disagreement at a time ----------------------------------
#
# The same disagreements the mouse pages list, turned into questions with a
# few answers each, so settling them is a stack of cards rather than a wall
# of text. A card's id is the conflict id the mouse page uses ("kind:what"),
# so an answer given here shows there too. Answers are ordinary notes with a
# 'choice'; nothing here edits a source.

SHORT = [("Handwritten notebook", "Notebook page"), ("notebookFeb-Jun", "Typed notebook"),
         ("Jarvis registry", "Recording files"), ("KCNT1_~1.CSV", "Recording folder list"),
         ("Channel Data", "DS sheet channel list"), ("Dentate Spike Data", "DS sheet"),
         ("KCNT1 Active 2.0", "Lab Ops sheet"), ("KCNT1 Active (Archived", "Lab Ops sheet (old tab)"),
         ("Sanity Check", "Lab Ops sheet (older tab)"), ("KCNT1 Archive", "Lab Ops archive tab"),
         ("Lab calendar", "Lab calendar"), ("Lab Notebook Import", "Lab Ops notebook import"),
         ("Recording Binder Import", "Lab Ops binder import"), ("Lab Operations Schedule", "Lab Ops sheet"),
         ("SoftMouse", "SoftMouse"), ("VOS census", "VOS cage card"), ("Jarvis mouse book", "Jarvis mouse book"),
         ("Kcnt1 workflow", "Dylan's tracker"), ("Colony_Count_092426", "Colony count (Sept 2026)"),
         ("Brain Bank", "Brain bank list"), ("KCNT1 AA Ages", "AA ages sheet"),
         ("Genotype List", "Genotype list"), ("Pten Blind", "PTEN blind roster"),
         ("Pten 2KO Unblind", "PTEN unblinded roster"), ("Mice.xlsx", "PTEN 2023 roster"),
         ("PTEN Recordings", "PTEN recordings sheet"), ("Mouse Recording Sessions", "IED session list"),
         ("bad channels", "Bad-channel list")]
KIND_ORDER = {"order": 0, "session": 1, "dates": 2, "disagree": 3}
ATTR_Q = {"sex": "What sex is {m}?", "dob": "When was {m} born?", "cage": "Which cage card is {m} on?",
          "alive": "Is {m} alive?", "role": "What is {m}'s role in the colony?",
          "parents": "Who are {m}'s parents?", "cohort": "Which cohort is {m} in?",
          "YH": "What is {m}'s YH genotype?", "SST": "What is {m}'s SST-Cre genotype?",
          "PV": "What is {m}'s PV-Cre genotype?"}
TYPE_WORDS = {"surgery_headplate": "headplate surgery", "probe_implant": "probe", "injection": "injection",
              "perfusion": "perfusion", "death": "end", "tail_snip": "tail snip"}


def short_source(s):
    s = s or ""
    for pat, word in SHORT:
        if pat.lower() in s.lower():
            return word
    return s.rsplit("/", 1)[-1].strip() or s


def _label(key):
    return key.replace("KCNT1:", "KCNT1 ").replace("PTEN:", "PTEN ")


def _nice(d):
    try:
        x = time.strptime(str(d)[:10], "%Y-%m-%d")
        return time.strftime("%b %d, %Y", x).replace(" 0", " ")
    except ValueError:
        return str(d)


def _evidence(fs, n=3):
    out = []
    for f in fs[:n]:
        out.append({"source": short_source(f.get("source")), "where": f.get("locator"),
                    "date": f.get("date"), "text": " -- ".join(x for x in (f.get("value"), f.get("detail")) if x)[:600],
                    "image": (f.get("images") or [None])[0]})
    return out


def _cards_for(d, facts):
    m = _label(d["key"])
    cards, order = [], []
    for c in d.get("conflicts") or []:
        cid = c["kind"] + ":" + c["what"]
        fs = [facts[i] for i in c.get("facts") or [] if i in facts]
        if c["kind"] == "disagree":
            vals = ((d.get("attrs") or {}).get(c["what"]) or {}).get("values") or []
            opts = [{"value": v["value"], "label": _nice(v["value"]) if c["what"] == "dob" else v["value"],
                     "sources": sorted({short_source(s) for s in v["sources"]}),
                     "facts": v["facts"][:3]} for v in vals[:4]]
            q = ATTR_Q.get(c["what"], "What is {m}'s %s?" % c["what"]).format(m=m)
        elif c["kind"] in ("dates", "session"):
            by = {}
            for f in fs:
                if f.get("date"):
                    by.setdefault(f["date"], []).append(f)
            opts = [{"value": dt, "label": _nice(dt), "sources": sorted({short_source(f.get("source")) for f in g}),
                     "facts": [f["id"] for f in g][:3]} for dt, g in sorted(by.items())][:4]
            what = c["what"].strip()
            if c["kind"] == "session":
                q = "When was {m}'s {w} recorded?".format(m=m, w=what)
            else:
                t, _, extra = what.partition(" ")
                q = "When was {m}'s {w}?".format(m=m, w=(TYPE_WORDS.get(t, t.replace("_", " ")) + (" " + extra if extra else "")).strip())
        else:
            order.append((c, fs))
            continue
        if len(opts) < 2:
            continue
        cards.append({"id": cid, "key": d["key"], "mouse": m, "kind": c["kind"], "question": q,
                      "options": opts, "evidence": _evidence(fs), "focus": d.get("focus")})
    if order:
        # Many 'after its end' rows are one story; one card for all of them.
        dates = sorted({f.get("date") for _, fs in order for f in fs if f.get("date")})
        end = next((r["date"] for r in d.get("timeline") or [] if r["type"] in ("death", "perfusion")), None)
        allf = [f for _, fs in order for f in fs]
        cards.append({
            "id": "order:" + ",".join(sorted({c["what"] for c, _ in order})), "key": d["key"], "mouse": m,
            "kind": "order", "focus": d.get("focus"),
            "question": "{m} has {n} record{s} dated after its end{e}. Which is it?".format(
                m=m, n=len(dates), s="" if len(dates) == 1 else "s",
                e=(" (%s)" % _nice(end)) if end else ""),
            "subtitle": "Dated " + (_nice(dates[0]) if len(dates) == 1 else
                                    "%s to %s" % (_nice(dates[0]), _nice(dates[-1]))),
            "options": [{"value": "other mouse", "label": "That record belongs to another mouse"
                         if len(dates) == 1 else "Those records belong to another mouse",
                         "sources": [], "facts": []},
                        {"value": "end wrong", "label": "The end date is wrong", "sources": [], "facts": []},
                        {"value": "dates wrong", "label": "That date is a typo" if len(dates) == 1
                         else "Those dates are typos", "sources": [], "facts": []}],
            "evidence": _evidence(allf)})
    return cards


LEVELS = [(0, "Egg"), (10, "Hatchling"), (40, "Chick"), (100, "Pullet"), (200, "Hen"),
          (350, "Rooster"), (600, "Coop Boss"), (1000, "Chicken Whisperer")]


def quest(scope="focus", limit=25):
    c = _load()
    if not c:
        return {"ok": True, "ready": False, "cards": []}
    person = ((WHO["fn"] or (lambda: (None, None)))() or (None, None))[0]
    answered = {(n.get("key"), n.get("conflict")) for n in _notes() if n.get("conflict")}
    mine = sum(1 for n in _notes() if n.get("conflict") and n.get("by") == person)
    facts = c["facts"]
    cards = []
    for d in c["dossiers"].values():
        if scope == "focus" and not d.get("focus"):
            continue
        for card in _cards_for(d, facts):
            card["done"] = (card["key"], card["id"]) in answered
            cards.append(card)
    cards.sort(key=lambda k: (not k["focus"], KIND_ORDER.get(k["kind"], 9), k["key"]))
    todo = [k for k in cards if not k["done"]]
    for k in todo[:limit]:
        for o in k["options"]:
            o["preview"] = [short_source(facts[i].get("source")) + ": " +
                            " -- ".join(x for x in (facts[i].get("value"), facts[i].get("detail")) if x)[:300]
                            for i in o.pop("facts") if i in facts]
    per_mouse = {}
    for k in cards:
        p = per_mouse.setdefault(k["key"], [0, 0])
        p[1] += 1
        p[0] += k["done"]
    level = max((lv for lv in LEVELS if mine * 10 >= lv[0]), key=lambda lv: lv[0])
    nxt = next((lv for lv in LEVELS if lv[0] > mine * 10), None)
    return {"ok": True, "ready": True, "cards": todo[:limit], "total": len(cards),
            "done": len(cards) - len(todo), "mice_total": len(per_mouse),
            "mice_cleared": sum(1 for a, b in per_mouse.values() if a == b),
            "me": {"name": person, "answered": mine, "points": mine * 10, "level": level[1],
                   "next_level": nxt and {"name": nxt[1], "at": nxt[0]}}}


def install(app, fail, who=None):
    WHO["fn"] = who

    @app.route("/api/chickenscratch/quest")
    def api_cs_quest():
        try:
            return jsonify(quest(request.args.get("scope") or "focus",
                                 int(request.args.get("limit") or 25)))
        except Exception as e:                           # noqa: BLE001
            return fail("chicken scratch quest", e)

    @app.route("/api/chickenscratch/index")
    def api_cs_index():
        try:
            return jsonify(index())
        except Exception as e:                           # noqa: BLE001
            return fail("chicken scratch index", e)

    @app.route("/api/chickenscratch/mouse")
    def api_cs_mouse():
        got = mouse(request.args.get("key") or "")
        if not got:
            return jsonify({"ok": False, "error": "no such mouse in Chicken Scratch"}), 404
        return jsonify(got)

    @app.route("/api/chickenscratch/notes")
    def api_cs_notes():
        return jsonify({"ok": True, "notes": _notes()})

    @app.route("/api/chickenscratch/note", methods=["POST"])
    def api_cs_note():
        try:
            return jsonify({"ok": True, "note": add_note(request.get_json(silent=True) or {})})
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/chickenscratch/image")
    def api_cs_image():
        p = os.path.abspath(request.args.get("path") or "")
        if not p.startswith(os.path.abspath(W) + os.sep) or not os.path.isfile(p):
            return jsonify({"ok": False, "error": "not a Chicken Scratch image"}), 404
        return send_file(p)
