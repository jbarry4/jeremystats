# -*- coding: utf-8 -*-
"""Every fact, from every source, into one dossier per mouse -- with the
disagreements kept, not settled.

Reads <work>/facts/*.jsonl (structured.py and the reading agents), writes
<work>/facts_all.json (every fact with an id) and <work>/dossiers.json:

  key -> {project, focus, raw_ids, attrs, timeline, sessions, conflicts,
          sources, n_facts}

attrs     one entry per attribute (sex, dob, YH/SST/PV, cage, role, alive,
          parents, cohort): every value any source gave, which sources, and
          the agreed value when there is one.
timeline  dated events, same-day same-kind facts folded together so a
          headplate seen in the sheet, the calendar and a notebook photo is
          one row with three sources.
conflicts the things a person has to look at: values that disagree, the
          same procedure on different dates, events in an impossible order,
          a session the notebook dates differently from the acquisition
          system.
"""
import collections
import datetime as dt
import glob
import hashlib
import json
import os
import re

W = os.path.expandvars(r"%LOCALAPPDATA%\Jarvis\chickenscratch")

# How much a source is believed on a date, highest first. The acquisition
# system's clock beats anything typed; a handwritten note made on the day
# beats a tracker filled in later; the calendar was planned, not observed.
RANK = [("Jarvis registry", 9), ("Channel Data", 8), ("Lab Notebook Import", 7),
        ("Recording Binder Import", 7), ("recording", 6), ("KCNT1 Active 2.0", 6),
        ("SoftMouse", 6), ("VOS census", 6), ("KCNT1 Archive", 5),
        ("KCNT1 Active (Archived", 5), ("Sanity Check", 4), ("calendar", 3)]
SINGLE = ("sex", "dob", "role", "alive", "cage", "parents")
EVENT = ("tail_snip", "injection", "behavior", "surgery_headplate", "probe_implant",
         "surgery_other", "recording_session", "drug", "seizure", "health", "death",
         "perfusion", "histology", "brain_bank", "calendar", "shipment", "exclusion",
         "census")
GENE = re.compile(r"\b(YH|SST|PV)(?:-Cre)?\s*[=(:]\s*\(?\s*(WT|Het|Hom|N/?A|Unknown|\?)", re.I)


def rank(f):
    s = f.get("source") or ""
    for pat, r in RANK:
        if pat.lower() in s.lower():
            return r
    return 5 if f.get("origin") == "agent" else 4


def norm_key(k):
    if not k:
        return None
    k = k.strip()
    m = re.fullmatch(r"(KCNT1)\s*:\s*[Mm]?-?0*(\d+)", k)
    if m:
        return "KCNT1:" + m.group(2)
    m = re.fullmatch(r"(PTEN)\s*:\s*[Mm]?0*(\d+)(.*)", k)
    if m:
        return "PTEN:m" + m.group(2) + m.group(3)
    return k


def load():
    facts = []
    for p in sorted(glob.glob(os.path.join(W, "facts", "*.jsonl"))):
        with open(p, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    f = json.loads(line)
                except ValueError:
                    continue
                f["key"] = norm_key(f.get("key"))
                if not f["key"] or f["key"].endswith(":?"):
                    f["key"] = f.get("key") or "UNKNOWN"
                f["file"] = os.path.basename(p)
                f["id"] = hashlib.sha1((p + str(i) + line).encode()).hexdigest()[:12]
                f["rank"] = rank(f)
                facts.append(f)
    return facts


def gene_votes(f):
    out = []
    for g, v in GENE.findall(" ".join(str(x or "") for x in (f.get("value"), f.get("detail")))):
        v = {"wt": "WT", "het": "Het", "hom": "Hom", "n/a": "N/A", "na": "N/A",
             "unknown": "Unknown", "?": "Unknown"}[v.lower()]
        out.append((g.upper(), v))
    return out


def attr_value(f):
    v = str(f.get("value") or "").strip()
    t = f["type"]
    if "=" in v and t in SINGLE:
        v = v.split("=", 1)[1].strip()
    if t == "cage":
        v = re.sub(r"^SoftMouse cage\s*", "", v)
    if t == "alive":
        v = {"yes": "alive", "alive": "alive", "no": "not alive", "dead": "not alive",
             "deceased": "not alive"}.get(v.lower(), v)
    if t == "role":
        v = v.capitalize() if v.lower() in ("stock", "mating", "ended", "breeder", "weanling") else v
    if t == "sex":
        v = v.upper()[:1] if v.lower() in ("m", "f", "male", "female") else v
        return {"M": "M", "F": "F"}.get(v, v)
    if t == "dob":
        if f.get("date"):
            return f["date"]
        for fmt in ("%m-%d-%Y", "%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return dt.datetime.strptime(v, fmt).date().isoformat()
            except ValueError:
                pass
        return v
    if t == "alive":
        return v
    return v


def pten_cohorts(facts, focus):
    """PTEN numbering restarts, so an m-number is not an animal. The focus
    sheet's Channel Data says which recording folders are 'the' m1; registry
    recordings in other folder families, far from those dates, are filed
    under 'PTEN:m1 (other: <year>)' so they never colour m1's story."""
    anchor = collections.defaultdict(lambda: {"roots": set(), "years": set()})
    for f in facts:
        if f["type"] == "recording_session" and "Channel Data" in (f.get("source") or ""):
            folder = (f.get("detail") or "").replace("folder: ", "")
            parts = re.split(r"[\\/]", folder)
            anchor[f["key"]]["roots"].update(p.lower() for p in parts[-3:-1] if p)
            m = re.search(r"(20\d\d)-\d\d-\d\d", folder)
            if m:
                anchor[f["key"]]["years"].add(int(m.group(1)))
    for f in facts:
        k = f["key"]
        if not k.startswith("PTEN:") or k not in anchor or not anchor[k]["years"]:
            continue
        if not f.get("source", "").startswith("Jarvis registry"):
            continue
        folders = (f.get("detail") or "").lower()
        same_root = any(r and r in folders for r in anchor[k]["roots"])
        y = int(f["date"][:4]) if f.get("date") else None
        if same_root:
            continue
        if y and min(abs(y - a) for a in anchor[k]["years"]) >= 1:
            f["key_was"] = k
            f["key"] = "%s (other animal, %d)" % (k, y)


def fold_timeline(fs):
    rows = collections.OrderedDict()
    for f in sorted(fs, key=lambda f: (f.get("date") or "9999", f["type"], -f["rank"])):
        if f["type"] not in EVENT or not f.get("date"):
            continue
        sig = (f["date"], f["type"], (f.get("session") or "").lstrip("s0") if f["type"] ==
               "recording_session" else _what(f))
        r = rows.setdefault(sig, {"date": f["date"], "type": f["type"], "what": _what(f),
                                  "session": f.get("session"), "facts": [], "sources": []})
        r["facts"].append(f["id"])
        if f.get("source") not in r["sources"]:
            r["sources"].append(f.get("source"))
    out = list(rows.values())
    # A probe the archived tracker gives without a side is the sided one
    # the current tracker gives the same day.
    sided = {(r["date"], r["what"].split(" (")[0]): r for r in out
             if r["type"] == "probe_implant" and " (" in r["what"]}
    keep = []
    for r in out:
        if r["type"] == "probe_implant" and " (" not in r["what"] and (r["date"], r["what"]) in sided:
            t = sided[(r["date"], r["what"])]
            t["facts"] += r["facts"]
            t["sources"] += [s for s in r["sources"] if s not in t["sources"]]
            continue
        keep.append(r)
    return keep


def _what(f):
    v = (f.get("value") or "").strip()
    t = f["type"]
    if t == "probe_implant":
        m = re.search(r"(H3|H10|H1)\b\s*(opto)?", v, re.I)
        side = re.search(r"\((L|R)\)|\b(left|right)\b", v, re.I)
        if not m:
            return v
        name = m.group(1).upper() + (" opto" if m.group(2) else "")
        if side:
            name += " (%s)" % (side.group(1) or side.group(2)[0]).upper()
        return name
    if t == "behavior":
        return re.sub(r"\s*#?\d*$", "", v)[:40]
    return t


def conflicts_for(key, fs, attrs, timeline):
    out = []
    for a, d in attrs.items():
        vals = [v for v in d["values"] if v["value"] not in ("", "Unknown", "?", "N/A") or a in ("YH", "SST", "PV")]
        distinct = {v["value"] for v in vals if v["value"] not in ("", "Unknown", "?")}
        if len(distinct) > 1:
            out.append({"kind": "disagree", "what": a,
                        "text": "%s: sources disagree -- %s" % (a, "; ".join(
                            "%s (%s)" % (v["value"], ", ".join(v["sources"][:3])) for v in d["values"])),
                        "facts": [i for v in d["values"] for i in v["facts"]]})
    # one procedure, several dates
    by = collections.defaultdict(list)
    for r in timeline:
        if r["type"] in ("surgery_headplate", "injection", "perfusion", "death", "tail_snip") or \
                r["type"] == "probe_implant":
            by[(r["type"], r["what"] if r["type"] == "probe_implant" else "")].append(r)
    for (t, what), rs in by.items():
        dates = sorted({r["date"] for r in rs})
        if len(dates) > 1 and t not in ("tail_snip",):
            d0, d1 = _d(dates[0]), _d(dates[-1])
            if d0 and d1 and (d1 - d0).days <= 120:
                out.append({"kind": "dates", "what": "%s %s" % (t, what),
                            "text": "%s%s is dated %s by different sources" % (
                                t.replace("_", " "), (" " + what) if what else "",
                                " vs ".join("%s (%s)" % (r["date"], ", ".join(r["sources"][:2])) for r in rs)),
                            "facts": [i for r in rs for i in r["facts"]]})
    # impossible order
    dob = attrs.get("dob", {}).get("agreed")
    death = [r["date"] for r in timeline if r["type"] in ("death", "perfusion")]
    dd = _d(dob) if dob else None
    for r in timeline:
        d = _d(r["date"])
        if not d:
            continue
        if dd and d < dd and r["type"] not in ("census", "calendar"):
            out.append({"kind": "order", "what": r["type"],
                        "text": "%s on %s is before the date of birth %s" % (r["type"], r["date"], dob),
                        "facts": r["facts"]})
        if death and r["type"] in ("recording_session", "surgery_headplate", "probe_implant",
                                   "injection", "behavior"):
            first_death = min(_d(x) for x in death if _d(x)) if any(_d(x) for x in death) else None
            if first_death and d > first_death + dt.timedelta(days=1):
                out.append({"kind": "order", "what": r["type"],
                            "text": "%s on %s is after the animal's end (%s)" % (
                                r["type"], r["date"], first_death.isoformat()),
                            "facts": r["facts"]})
    # a session dated differently by the notes and by the acquisition system
    sess = collections.defaultdict(lambda: collections.defaultdict(set))
    for f in fs:
        if f["type"] == "recording_session" and f.get("session") and f.get("date"):
            s = re.sub(r"^[sS]0*", "", str(f["session"]).split(",")[0].strip())
            sess[s][f["date"]].add(f.get("source"))
    for s, dates in sess.items():
        if len(dates) > 1:
            ds = sorted(dates)
            if (_d(ds[-1]) - _d(ds[0])).days <= 60 if _d(ds[0]) and _d(ds[-1]) else False:
                out.append({"kind": "session", "what": "session %s" % s,
                            "text": "session %s is dated %s" % (s, " vs ".join(
                                "%s (%s)" % (d, ", ".join(sorted(x for x in dates[d] if x))[:80]) for d in ds)),
                            "facts": [f["id"] for f in fs if f["type"] == "recording_session"
                                      and re.sub(r"^[sS]0*", "", str(f.get("session") or "").split(",")[0].strip()) == s]})
    return out


def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def main():
    facts = load()
    focus = json.load(open(os.path.join(W, "focus.json"), encoding="utf-8"))
    pten_cohorts(facts, focus)
    by = collections.defaultdict(list)
    for f in facts:
        by[f["key"]].append(f)
    dossiers = {}
    for key, fs in by.items():
        attrs = collections.OrderedDict()

        def vote(name, value, f):
            if value in (None, ""):
                return
            a = attrs.setdefault(name, {"values": []})
            for v in a["values"]:
                if v["value"].lower() == str(value).lower():
                    v["facts"].append(f["id"])
                    if f.get("source") not in v["sources"]:
                        v["sources"].append(f.get("source"))
                    v["rank"] = max(v["rank"], f["rank"])
                    return
            a["values"].append({"value": str(value), "facts": [f["id"]],
                                "sources": [f.get("source")], "rank": f["rank"]})
        for f in fs:
            if f["type"] == "cage" and attr_value(f).upper() in ("RETIRED", "N/A", "?"):
                continue
            if f["type"] in SINGLE:
                vote(f["type"], attr_value(f), f)
            if f["type"] == "genotype" or f["type"] == "identity":
                for g, v in gene_votes(f):
                    vote(g, v, f)
            if f.get("cohort"):
                vote("cohort", f["cohort"], f)
        for name, a in attrs.items():
            a["values"].sort(key=lambda v: (-len(v["sources"]), -v["rank"]))
            top = a["values"][0]
            a["agreed"] = top["value"] if len(a["values"]) == 1 or (
                len(top["sources"]) > len(a["values"][1]["sources"])) else None
        timeline = fold_timeline(fs)
        sessions = collections.defaultdict(list)
        for f in fs:
            if f["type"] in ("recording_session", "analysis") and f.get("session"):
                s = re.sub(r"^[sS]0*", "", str(f["session"]).split(",")[0].strip()) or "?"
                sessions[s].append(f["id"])
        dossiers[key] = {
            "key": key, "project": key.split(":")[0], "focus": key in focus,
            "focus_sessions": (focus.get(key) or {}).get("sessions"),
            "raw_ids": sorted({str(f.get("raw")) for f in fs if f.get("raw")})[:20],
            "attrs": attrs, "timeline": timeline,
            "sessions": {k: v for k, v in sorted(sessions.items(), key=lambda kv: (len(kv[0]), kv[0]))},
            "conflicts": conflicts_for(key, fs, attrs, timeline),
            "sources": sorted(collections.Counter(f.get("source") for f in fs).items(),
                              key=lambda kv: -kv[1]),
            "n_facts": len(fs),
            "facts": [f["id"] for f in fs],
        }
    with open(os.path.join(W, "facts_all.json"), "w", encoding="utf-8") as fh:
        json.dump({f["id"]: f for f in facts}, fh, ensure_ascii=False)
    with open(os.path.join(W, "dossiers.json"), "w", encoding="utf-8") as fh:
        json.dump(dossiers, fh, ensure_ascii=False)
    nf = sum(1 for d in dossiers.values() if d["focus"])
    print("facts %d, mice %d (focus %d), conflicts %d (focus %d)" % (
        len(facts), len(dossiers), nf, sum(len(d["conflicts"]) for d in dossiers.values()),
        sum(len(d["conflicts"]) for d in dossiers.values() if d["focus"])))


if __name__ == "__main__":
    main()
