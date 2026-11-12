"""
weekly.py -- "Last 7 days' work": a printout of the week, for the PI.

Press the printer on Inside Jarvis and this gathers what the lab did in the
last seven days:

  * the code: commits and the lines they changed, by part of the app, and
    every version the patch notes shipped;
  * the data: what was banked, what was called in the curation sets and by
    whom, the recordings that arrived, who was working;
  * the bench: the Lab Operations sheet's dated procedures (surgeries,
    implants, behaviour, perfusions, sectioning), read from its link the
    way tools/appscript.py reads it, and the colony as it stands.

Then Hater of AI (floss.py's engine, here with read-only tools) reads all of
it, may open the code it names, and writes a short, calm summary of the
progress for the PI. If he cannot be asked on this computer, Jarvis writes
the summary from the numbers and says so on the printout.

Every printout is GUI_logs/weekly/<id>@<shard>.json, written once by the
computer that printed it, so it travels by git and anyone can read the last
one. A printing in progress is registered here (RUN), and the page finds it
again whenever it is shown.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from . import feed
from . import floss as flossmod
from . import floss_key as keymod
from .paths import APP_DIR, LOGS_DIR, REPO_ROOT

NAME = flossmod.NAME
DAYS = 7
REPORTS = os.path.join(LOGS_DIR, "weekly")
RUNLOGS = os.path.join(keymod.STATE, "weekly")
MODEL = flossmod.MODEL
MAX_TURNS = 24
TIMEOUT_S = 10 * 60

# The Lab Operations Schedule, the tab the VOS and SoftMouse imports keep.
# Anyone with its link can read it, which is how this reads it: no sign-in.
SHEET_ID = "1SDXG1GpRhkjq2aKri3n06nOuR8TGio9QuQsyN656ERo"
SHEET_GID = "1444923131"
SHEET_URL = "https://docs.google.com/spreadsheets/d/%s/edit#gid=%s" % (SHEET_ID, SHEET_GID)
SHEET_CSV = ("https://docs.google.com/spreadsheets/d/%s/gviz/tq?tqx=out:csv&headers=1&gid=%s"
             % (SHEET_ID, SHEET_GID))

RUN = {"running": False, "id": None, "steps": [], "started": None, "proc": None,
       "stopped": False}
_LOCK = threading.Lock()
HOOKS = {"who": None, "machine": None, "shard": None, "reg": None, "bank": None,
         "curate": None, "is_test": None, "save": None}

RULES = """\
You are "Hater of AI", the in-app helper of Jarvis, a neuroscience lab's
workbench (a Flask backend in backend/, a browser front end in web/, scripts
in tools/; your working directory is the app folder). This time you are not
fixing anything. You are writing the lab's weekly progress note for the PI,
from the week's record you are given. You may open the code or the patch
notes it names to understand a change; you cannot change anything.

The reader is the lab's principal investigator: a scientist, busy, and
responsible for the whole lab. Your note should leave them calm and well
informed: it says plainly what got done, what it means for the science, and
what is in hand next. Write it the way a trusted lab manager would:

- Lead with what was accomplished. Group the week into a few themes rather
  than listing every version.
- Say what each change makes possible for the research, in plain words. No
  code names without a short plain gloss ("Root Canal, which separates
  dentate spikes from P-spikes"), no file names, no jargon, no hype.
- Use the real numbers you are given, and only those. Never invent a
  result, a date, a person or a plan. If the week was quiet in some area,
  say so simply.
- Anything unfinished or uncertain is said honestly, with what is already
  being done about it. Calm, never alarming, never hidden.
- The bench work (from the lab sheet) is part of the progress: surgeries,
  implants, recordings, behaviour, histology. Name who led it only as the
  sheet does.
- Short: the whole note reads in under two minutes.

Finish with exactly one fenced json block, nothing after it:
```json
{"headline": "one calm sentence that sums up the week",
 "summary": "three or four sentences for the PI",
 "progress": ["the week's main advances, one plain sentence each, at most 6"],
 "bench": ["what happened at the bench, one sentence each, at most 4"],
 "data": ["what happened to the data, one sentence each, at most 3"],
 "next": ["what is in hand for next week, at most 4"],
 "watch": ["anything worth keeping an eye on, with what is being done about it; may be empty"]}
```
"""


# --- small things ---------------------------------------------------------------------

def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _hook(name, default=None):
    fn = HOOKS.get(name)
    if not fn:
        return default
    try:
        return fn()
    except Exception:                                    # noqa: BLE001
        return default


def _step(text):
    with _LOCK:
        RUN["steps"].append({"at": time.time(), "text": text})
        del RUN["steps"][:-40]
    feed.say("Last 7 days: " + text, kind="weekly", key="weekly")


def _when(stamp):
    """Any stamp the records use -> an aware datetime, or None."""
    if not stamp:
        return None
    s = str(stamp).strip()
    if re.search(r"[+-]\d{4}$", s):
        s = s[:-2] + ":" + s[-2:]
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.astimezone()


def _shard():
    return _hook("shard", "") or "here"


def _person(name):
    if not name:
        return False
    test = HOOKS.get("is_test")
    if test and test(name):
        return False
    return str(name).strip().lower() not in ("snapshot import", "unknown", "debug_bot")


# --- the code ---------------------------------------------------------------------------

AREAS = (("_Jarvis/app/backend/", "the server"),
         ("_Jarvis/app/web/_dev/", "the checks"),
         ("_Jarvis/app/web/", "the interface"),
         ("_Jarvis/app/tools/", "the scripts"),
         ("_Jarvis/app/GUI_logs/", "the shared records"),
         ("_Jarvis/app/", "the notes and docs"))


def _area(path):
    for pre, name in AREAS:
        if path.startswith(pre):
            return name
    return "elsewhere"


def _git(args, timeout=90):
    r = subprocess.run(["git", "-c", "core.longpaths=true"] + list(args), cwd=REPO_ROOT,
                       capture_output=True, timeout=timeout,
                       creationflags=flossmod._NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:300])
    return r.stdout.decode("utf-8", "replace")


def gather_code(since):
    out = {"commits": 0, "authors": {}, "areas": {}, "files": 0, "added": 0, "removed": 0,
           "records_changed": 0, "uncommitted": 0, "versions": []}
    try:
        log = _git(["log", "--since=" + since.isoformat(), "--format=@@%H\t%an",
                    "--numstat", "--", "_Jarvis", "BARRY GUI"])
    except Exception as e:                               # noqa: BLE001
        out["error"] = str(e)
        log = ""
    authors, areas, files = Counter(), defaultdict(lambda: [0, 0, 0]), set()
    for ln in log.splitlines():
        if ln.startswith("@@"):
            out["commits"] += 1
            authors[ln.split("\t", 1)[-1]] += 1
            continue
        bits = ln.split("\t")
        if len(bits) != 3:
            continue
        a, r, path = bits
        path = re.sub(r"\{[^}]*=> ([^}]*)\}", r"\1", path).replace("BARRY GUI/", "_Jarvis/app/")
        where = _area(path)
        if where == "the shared records":
            out["records_changed"] += 1
            continue
        a, r = (int(a) if a.isdigit() else 0), (int(r) if r.isdigit() else 0)
        if not a and not r:
            # Moved, not changed: the folder move of 2026-11-03 renamed
            # every file in the app, and none of that is work done.
            continue
        areas[where][0] += a
        areas[where][1] += r
        if path not in files:
            areas[where][2] += 1
            files.add(path)
        out["added"] += a
        out["removed"] += r
    out["files"] = len(files)
    out["authors"] = dict(authors.most_common())
    out["areas"] = {k: {"added": v[0], "removed": v[1], "files": v[2]}
                    for k, v in sorted(areas.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))}
    try:
        st = _git(["status", "--porcelain", "--", "_Jarvis"])
        out["uncommitted"] = sum(1 for ln in st.splitlines()
                                 if ln[3:] and "GUI_logs/" not in ln[3:])
    except Exception:                                    # noqa: BLE001
        pass
    # The patch notes are the week told in words: every version since.
    from . import inside as insidemod
    try:
        with open(os.path.join(APP_DIR, "CHANGELOG.md"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    first = since.date().isoformat()
    bodies = re.split(r"(?m)^(?=## \d{4}\.\d{2}\.\d{2}\.\d+)", text)
    for v in insidemod.parse_changelog(text):
        if v["day"] >= first:
            body = next((b for b in bodies if b.startswith("## " + v["v"])), "")
            out["versions"].append({"v": v["v"], "day": v["day"], "title": v["title"],
                                    "words": v["words"], "body": body.strip()})
    out["versions"].sort(key=lambda v: v["v"])
    return out


# --- the data ---------------------------------------------------------------------------

def gather_data(since):
    out = {}
    try:
        kinds, entries, versions, savers = Counter(), 0, 0, Counter()
        for e in _hook("bank").all():
            at = _when((e.get("added") or {}).get("at"))
            if at and at >= since:
                entries += 1
                kinds[str(e.get("type") or "other")] += len(e.get("events") or [])
            for v in e.get("versions") or []:
                vat = _when((v or {}).get("at"))
                if vat and vat >= since:
                    versions += 1
                    if _person(v.get("by")):
                        savers[v.get("by")] += 1
        out["bank"] = {"entries": entries, "events": dict(kinds), "versions": versions,
                       "by": dict(savers.most_common())}
    except Exception as e:                               # noqa: BLE001
        out["bank"] = {"error": str(e)}
    try:
        people, models, labels, sets_touched = Counter(), Counter(), Counter(), set()
        for s in _hook("curate").all():
            for ev in s.get("events") or []:
                for rv in (ev or {}).get("reviews") or []:
                    at = _when((rv or {}).get("at"))
                    if not at or at < since:
                        continue
                    by = str(rv.get("by") or "")
                    sets_touched.add(s.get("name") or s.get("gid"))
                    labels[str(rv.get("label"))] += 1
                    if by.endswith("(AI)"):
                        models[by] += 1
                    elif _person(by):
                        people[by] += 1
        out["calls"] = {"people": dict(people.most_common()), "models": dict(models.most_common()),
                        "labels": dict(labels.most_common()), "sets": len(sets_touched)}
    except Exception as e:                               # noqa: BLE001
        out["calls"] = {"error": str(e)}
    try:
        reg = _hook("reg")
        new = Counter()
        for r in reg.live():
            at = _when(r.get("created"))
            if at and at >= since:
                new[str(r.get("project") or "Unfiled")] += 1
        out["recordings"] = dict(new.most_common())
    except Exception as e:                               # noqa: BLE001
        out["recordings"] = {"error": str(e)}
    out["activity"] = _activity(since)
    out["floss"] = _floss_tickets(since)
    return out


def _activity(since):
    users, actions = Counter(), Counter()
    d = os.path.join(LOGS_DIR, "activity")
    first = since.date()
    try:
        names = os.listdir(d)
    except OSError:
        return {}
    for fn in names:
        try:
            if date.fromisoformat(fn[:10]) < first:
                continue
        except ValueError:
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as fh:
                for ln in fh:
                    try:
                        a = json.loads(ln)
                    except ValueError:
                        continue
                    at = _when(a.get("at"))
                    if not at or at < since or a.get("test") or not _person(a.get("user")):
                        continue
                    users[a.get("user")] += 1
                    actions[str(a.get("action") or "").split(".")[0]] += 1
        except OSError:
            continue
    return {"people": dict(users.most_common()), "areas": dict(actions.most_common(12)),
            "actions": sum(users.values())}


def _floss_tickets(since):
    c = Counter()
    for p in _glob(os.path.join(LOGS_DIR, "floss"), ".json"):
        try:
            with open(p, encoding="utf-8") as fh:
                t = json.load(fh)
        except (OSError, ValueError):
            continue
        at = _when(t.get("at"))
        if at and at >= since:
            c[str(t.get("status"))] += 1
    return dict(c)


def _glob(d, ext):
    try:
        return [os.path.join(d, n) for n in os.listdir(d) if n.endswith(ext)]
    except OSError:
        return []


# --- the bench --------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*$")


def _sheet_date(v):
    m = _DATE_RE.match(v or "")
    if not m:
        return None
    y = int(m.group(3))
    y = y + 2000 if y < 100 else y
    try:
        return date(y, int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def parse_sheet(text, first, last):
    """The sheet's dated procedures between two days, and the colony now.

    A procedure is any column followed by Time and Lead (and, for an
    implant, Sessions), so a column the lab adds next month is read too."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {"events": [], "colony": {}}
    head = [h.strip() for h in rows[0]]
    col = {h: i for i, h in reversed(list(enumerate(head)))}
    procs = []
    for i, h in enumerate(head):
        if h and h not in ("Time", "Lead", "Sessions") and head[i + 1:i + 3] == ["Time", "Lead"]:
            procs.append((i, h, i + 3 if head[i + 3:i + 4] == ["Sessions"] else None))
    events = []
    alive, roles = 0, Counter()
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        get = lambda i: r[i].strip() if i is not None and i < len(r) else ""   # noqa: E731
        mouse = get(0)
        if get(col.get("Alive")).lower() in ("yes", "y", "true"):
            alive += 1
            roles[get(col.get("Role")) or "unassigned"] += 1
        for i, name, si in procs:
            d = _sheet_date(get(i))
            if d and first <= d <= last:
                events.append({"day": d.isoformat(), "what": name, "mouse": mouse,
                               "cage": get(col.get("Cage ID")), "lead": get(i + 2),
                               "sessions": get(si) if si else ""})
    events.sort(key=lambda e: (e["day"], e["what"], e["mouse"]))
    return {"events": events, "colony": {"alive": alive, "roles": dict(roles.most_common())},
            "procedures": [p[1] for p in procs]}


def gather_bench(since):
    first, last = since.date(), date.today()
    try:
        req = urllib.request.Request(SHEET_CSV, headers={"User-Agent": "Jarvis"})
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", "replace")
    except Exception as e:                               # noqa: BLE001
        return {"error": "the Lab Operations sheet could not be read: %s" % e, "url": SHEET_URL}
    got = parse_sheet(text, first, last)
    got["url"] = SHEET_URL
    got["counts"] = dict(Counter(e["what"] for e in got["events"]).most_common())
    got["leads"] = dict(Counter(p.strip() for e in got["events"]
                                for p in re.split(r"[,&/]| and ", e["lead"]) if p.strip())
                        .most_common())
    return got


# --- numbers, for the printout and for the brief -----------------------------------------

def numbers(code, data, bench):
    bank, calls = data.get("bank") or {}, data.get("calls") or {}
    # Everyone with their name on something this week: a saved version, a
    # call, an action in Jarvis. The sheet's leads are counted on their own.
    people = set((bank.get("by") or {}).keys()) | set((calls.get("people") or {}).keys()) \
        | set(((data.get("activity") or {}).get("people") or {}).keys())
    people = {p for p in people if not str(p).endswith("(AI)")}
    return {
        "versions": len(code.get("versions") or []),
        "commits": code.get("commits", 0),
        "lines_added": code.get("added", 0),
        "lines_removed": code.get("removed", 0),
        "files": code.get("files", 0),
        "events_banked": sum((bank.get("events") or {}).values()),
        "entries_banked": bank.get("entries", 0),
        "bank_versions": bank.get("versions", 0),
        "calls_people": sum((calls.get("people") or {}).values()),
        "calls_models": sum((calls.get("models") or {}).values()),
        "recordings_new": sum(v for v in (data.get("recordings") or {}).values()
                              if isinstance(v, int)),
        "procedures": len(bench.get("events") or []),
        "people": len(people),
        "bench_people": len(bench.get("leads") or {}),
    }


def brief(since, until, code, data, bench, nums):
    """The week, as Hater of AI is given it."""
    L = ["# The week: %s to %s" % (since.date().isoformat(), until.date().isoformat()), "",
         "## Numbers", "```json", json.dumps(nums, indent=1), "```", "",
         "## Code, by part of the app (lines added / removed / files)"]
    for k, v in (code.get("areas") or {}).items():
        L.append("- %s: +%d / -%d in %d files" % (k, v["added"], v["removed"], v["files"]))
    L.append("- commits by: " + ", ".join("%s %d" % kv for kv in (code.get("authors") or {}).items()))
    if code.get("uncommitted"):
        L.append("- %d code files changed and not yet committed" % code["uncommitted"])
    L += ["", "## Data"]
    L.append("```json")
    L.append(json.dumps({k: data.get(k) for k in ("bank", "calls", "recordings", "activity", "floss")},
                        indent=1, default=str))
    L.append("```")
    L += ["", "## The bench (Lab Operations sheet, %s)" % ("could not be read: " + bench["error"]
                                                          if bench.get("error") else "read just now")]
    for e in bench.get("events") or []:
        L.append("- %s: %s on mouse %s%s%s" % (e["day"], e["what"], e["mouse"],
                                              ", led by " + e["lead"] if e["lead"] else "",
                                              ", sessions " + e["sessions"] if e["sessions"] else ""))
    if bench.get("colony"):
        L.append("- colony now: %s" % json.dumps(bench["colony"]))
    L += ["", "## The patch notes for every version this week (oldest first)"]
    budget = 90000
    vs = code.get("versions") or []
    for v in vs:
        body = v["body"]
        share = max(1500, budget // max(1, len(vs)))
        if len(body) > share:
            # Too long to give whole: its title and opening lines, and
            # the version's name, so he can open CHANGELOG.md for the rest.
            body = body[:share].rsplit("\n", 1)[0] + "\n(the rest is in CHANGELOG.md, version %s)" % v["v"]
        L += ["", body]
    return "\n".join(L)


def _n(v):
    return "{:,}".format(int(v or 0))


def _names(names):
    names = [n for n in names if n]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def plain_summary(nums, code, data, bench):
    """When Hater of AI cannot be asked: the same shape, from the numbers,
    in the same calm words. It says only what the numbers say."""
    vs = code.get("versions") or []
    calls = data.get("calls") or {}
    progress = ["%s (v%s)." % (v["title"].rstrip("."), v["v"]) for v in vs[-6:]]
    bench_lines = []
    by_what = defaultdict(list)
    for e in bench.get("events") or []:
        by_what[e["what"]].append(e)
    for what, evs in sorted(by_what.items(), key=lambda kv: -len(kv[1]))[:4]:
        leads = sorted({p.strip() for e in evs for p in re.split(r"[,&/]| and ", e["lead"]) if p.strip()})
        mice = len({e["mouse"] for e in evs})
        bench_lines.append("%s: %s, on %d %s%s." % (
            what, "%d %s" % (len(evs), "entry" if len(evs) == 1 else "entries"), mice,
            "mouse" if mice == 1 else "mice", ", led by " + _names(leads) if leads else ""))
    if not bench_lines:
        bench_lines = (["The lab sheet could not be read this time; nothing is lost, it will be "
                        "read again on the next printout."] if bench.get("error")
                       else ["No dated procedures on the lab sheet this week."])
    if bench.get("colony", {}).get("alive"):
        bench_lines.append("The colony stands at %s live mice." % _n(bench["colony"]["alive"]))
    head = ("A productive week: %s versions of Jarvis shipped, %s events banked, and %s calls "
            "made by people." % (_n(nums["versions"]), _n(nums["events_banked"]), _n(nums["calls_people"])))
    if not nums["versions"] and not nums["events_banked"]:
        head = "A quiet week in Jarvis; the records are as they were."
    return {
        "headline": head,
        "summary": ("Work went in on the code all week: %s commits changed %s lines across %s files. "
                    "The most recent changes: %s. The data grew alongside it, and every call in "
                    "the curation sets is kept with who made it."
                    % (_n(nums["commits"]), _n(nums["lines_added"] + nums["lines_removed"]),
                       _n(nums["files"]), "; ".join(v["title"].rstrip(".") for v in vs[-3:]) or "none")),
        "progress": progress,
        "bench": bench_lines,
        "data": ["%s new bank entries, and %s new versions of entries already banked."
                 % (_n(nums["entries_banked"]), _n(nums["bank_versions"])),
                 "Calls in the curation sets: %s by people and %s by models, across %s sets."
                 % (_n(nums["calls_people"]), _n(nums["calls_models"]), _n(calls.get("sets", 0)))],
        "next": [], "watch": [],
    }


# --- asking Hater of AI -------------------------------------------------------------------

def _command(exe, key, rules_file):
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose",
           "--model", MODEL, "--max-turns", str(MAX_TURNS),
           "--restricted", "--tools", "Read,Glob,Grep",
           "--allowedTools", "Read", "Glob", "Grep",
           "--permission-mode", "dontAsk", "--strict-mcp-config",
           "--no-session-persistence", "--append-system-prompt-file", rules_file]
    if keymod.kind_of(key) == "api":
        cmd += ["--max-budget-usd", "1"]
    return cmd


def _narrate(ev):
    if ev.get("type") != "assistant":
        return
    for b in (ev.get("message") or {}).get("content") or []:
        if b.get("type") == "tool_use":
            i, n = b.get("input") or {}, b.get("name")
            if n == "Read":
                p = str(i.get("file_path") or "")
                _step("%s is reading %s" % (NAME, os.path.relpath(p, APP_DIR) if os.path.isabs(p) else p))
            elif n in ("Grep", "Glob"):
                _step("%s is looking for “%s”" % (NAME, str(i.get("pattern"))[:80]))


def ask_hater(text, rid):
    """Hater of AI's note, or (None, why not)."""
    exe = flossmod.engine()
    if not exe:
        return None, "Claude Code is not on this computer", None
    key = keymod.here()
    if not key:
        return None, NAME + " is locked on this computer (the lab PIN unlocks him)", None
    os.makedirs(RUNLOGS, exist_ok=True)
    os.makedirs(flossmod.HOME, exist_ok=True)
    rules = os.path.join(RUNLOGS, rid + ".rules.md")
    with open(rules, "w", encoding="utf-8") as fh:
        fh.write(RULES)
    log = open(os.path.join(RUNLOGS, rid + ".jsonl"), "wb")
    err = open(os.path.join(RUNLOGS, rid + ".stderr.txt"), "wb")
    result = {}
    try:
        proc = subprocess.Popen(_command(exe, key, rules), cwd=APP_DIR, env=flossmod._env(key),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                creationflags=flossmod._NO_WINDOW,
                                start_new_session=not flossmod.WIN)
        with _LOCK:
            RUN["proc"] = proc
        proc.stdin.write(text.encode("utf-8"))
        proc.stdin.close()
        timer = threading.Timer(TIMEOUT_S, flossmod._kill, [proc])
        timer.daemon = True
        timer.start()
        for raw in proc.stdout:
            log.write(raw)
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            if ev.get("type") == "result":
                result = ev
            else:
                _narrate(ev)
        proc.wait()
        timer.cancel()
    finally:
        log.close()
        err.close()
        with _LOCK:
            RUN["proc"] = None
    run = {"model": MODEL, "turns": result.get("num_turns"), "cost_usd": result.get("total_cost_usd"),
           "seconds": round((result.get("duration_ms") or 0) / 1000.0, 1) or None}
    if RUN["stopped"]:
        return None, "the printing was stopped", run
    if not result or result.get("is_error"):
        return None, "%s could not finish: %s" % (NAME, str(result.get("result") or "no answer")[:300]), run
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", result.get("result") or "", re.S)
    try:
        note = json.loads(blocks[-1]) if blocks else None
    except ValueError:
        note = None
    if not isinstance(note, dict) or not note.get("headline"):
        return None, NAME + " answered, but not in the shape a printout needs", run
    keep = {}
    for k in ("headline", "summary"):
        keep[k] = str(note.get(k) or "").strip()
    for k in ("progress", "bench", "data", "next", "watch"):
        keep[k] = [str(x).strip() for x in (note.get(k) or []) if str(x).strip()][:8]
    return keep, None, run


# --- a printing ---------------------------------------------------------------------------

def _path(rid, shard=None):
    return os.path.join(REPORTS, "%s@%s.json" % (rid, shard or _shard()))


def _save(rep):
    os.makedirs(REPORTS, exist_ok=True)
    p = _path(rep["id"], rep.get("shard"))
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1, ensure_ascii=False)
    os.replace(p + ".tmp", p)


def _print(rid):
    until = datetime.now().astimezone()
    since = until - timedelta(days=DAYS)
    rep = {"id": rid, "shard": _shard(), "machine": _hook("machine"), "who": _hook("who"),
           "at": _now_iso(), "since": since.isoformat(timespec="seconds"),
           "until": until.isoformat(timespec="seconds"), "status": "printing"}
    try:
        _step("reading the last %d days of commits and patch notes" % DAYS)
        code = gather_code(since)
        _step("counting what was banked and called, and who worked")
        data = gather_data(since)
        _step("reading the Lab Operations sheet")
        bench = gather_bench(since)
        nums = numbers(code, data, bench)
        rep.update(numbers=nums, code={k: v for k, v in code.items() if k != "versions"},
                   versions=[{k: v[k] for k in ("v", "day", "title")} for v in code["versions"]],
                   data=data, bench=bench)
        if RUN["stopped"]:
            raise InterruptedError
        _step("%s is reading the week" % NAME)
        note, why, run = ask_hater(brief(since, until, code, data, bench, nums), rid)
        if RUN["stopped"]:
            raise InterruptedError
        if note:
            rep.update(note=note, writer=NAME, run=run)
        else:
            rep.update(note=plain_summary(nums, code, data, bench), writer="Jarvis",
                       why_plain=why, run=run)
        rep["status"] = "printed"
        _step("printed")
    except InterruptedError:
        rep.update(status="stopped")
    except Exception as e:                               # noqa: BLE001
        rep.update(status="failed", error=str(e)[:600])
    finally:
        try:
            _save(rep)
        except OSError as e:
            rep.update(status="failed", error="could not be kept: %s" % e)
        words = {"printed": "printed", "stopped": "was stopped",
                 "failed": "could not be printed: %s" % rep.get("error")}
        feed.say("Last 7 days' work " + words.get(rep["status"], rep["status"]), kind="weekly",
                 key="weekly", level="err" if rep["status"] == "failed" else "info", done=True)
        with _LOCK:
            RUN.update(running=False, proc=None)
    return rep


def print_now():
    """A printing, start to finish, in this thread: for tools/weekly_email.py,
    which runs with no server and no page."""
    with _LOCK:
        if RUN["running"]:
            raise RuntimeError("a printing is already running in this process")
        rid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        RUN.update(running=True, id=rid, steps=[], started=time.time(), stopped=False, proc=None)
    return _print(rid)


# --- the email ------------------------------------------------------------------------
#
# Sent from the lab's Google account by a small Apps Script web app of its
# own, "Jarvis Mailer" (mailer/Code.js), which holds only the hash of the
# secret and of each address it may send to. Where it is and the secret are
# on the computer that sends, never in git: %LOCALAPPDATA%\Jarvis\weekly\mail.json
#   {"url": ".../exec", "secret": "...", "lab": [addresses], "test": [addresses],
#    "schedule": "Fridays at 3:00 PM"}

MAIL_CONFIG = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                           "Jarvis", "weekly", "mail.json")


def mail_config():
    try:
        with open(MAIL_CONFIG, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def email_subject(rep):
    return "Barry Lab: the last 7 days (%s)" % (_span(rep) or "this week")


def why_words(why):
    """Why Hater of AI did not write it, in words for the PI rather than the
    engine's own message."""
    w = str(why or "").lower()
    if not w:
        return ""
    if "limit" in w or "quota" in w:
        return "Hater of AI had reached the lab account's usage limit for the moment"
    if "locked" in w or "pin" in w:
        return "Hater of AI is not unlocked on the computer that printed it"
    if "not on this computer" in w or "install" in w:
        return "Hater of AI is not installed on the computer that printed it"
    if "stopped" in w:
        return "the printing was stopped before Hater of AI finished"
    return "Hater of AI could not be asked this time"


def _span(rep, long=False):
    def one(s):
        d = datetime.fromisoformat(s)
        return (d.strftime("%A, %B ") if long else d.strftime("%b ")) + str(d.day)
    try:
        b = datetime.fromisoformat(rep["until"])
        return "%s to %s%s" % (one(rep["since"]), one(rep["until"]), ", %d" % b.year if long else "")
    except (KeyError, ValueError):
        return ""


def email_html(rep):
    """The printout as an email, laid out for a reader with two minutes:
    the headline, four numbers at a glance, the week in sections, the bench
    in a table, every version shipped, then the full numbers.

    Plain tables and inline styles only, which is what every mail client
    (Outlook included) draws the same; no images, nothing fetched."""
    from html import escape as e
    n, note = rep.get("numbers") or {}, rep.get("note") or {}
    G, G2, GOLD, INK, SOFT, FAINT, LINE, PAPER = ("#154734", "#1f5c44", "#FFB81C", "#0c1f17",
                                                  "#465c52", "#78907f", "#dbe6df", "#f4f7f5")
    F = "font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
    out = []

    def row(inner, pad="0 32px"):
        out.append('<tr><td style="padding:%s;%s">%s</td></tr>' % (pad, F, inner))

    def heading(title):
        return ('<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 10px">'
                '<tr><td style="width:4px;background:%s;border-radius:2px"></td>'
                '<td style="padding:2px 0 2px 10px;%sfont-size:12px;font-weight:700;letter-spacing:.12em;'
                'text-transform:uppercase;color:%s">%s</td></tr></table>' % (GOLD, F, G, e(title)))

    def bullets(items):
        return ('<table role="presentation" cellpadding="0" cellspacing="0" width="100%%">%s</table>'
                % "".join('<tr><td valign="top" style="width:18px;padding:3px 0;color:%s;font-size:15px;'
                          'line-height:1.55">&#9679;</td><td style="padding:3px 0;%sfont-size:15px;'
                          'line-height:1.55;color:%s">%s</td></tr>' % (GOLD, F, INK, e(x)) for x in items))

    # The inbox preview: the headline, not the first words of the layout.
    pre = e(note.get("headline") or "The week in the Barry Lab")
    out.append('<tr><td style="display:none;max-height:0;overflow:hidden;font-size:1px;line-height:1px;'
               'color:#ffffff">%s</td></tr>' % pre)
    # The band.
    out.append('<tr><td style="background:%s;padding:26px 32px 24px;%s">'
               '<div style="font-size:11px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;'
               'color:%s">Barry Lab &middot; Jarvis</div>'
               '<div style="font-size:26px;font-weight:700;color:#ffffff;margin-top:6px">'
               'Last 7 days&rsquo; work</div>'
               '<div style="font-size:14px;color:#cfe3d8;margin-top:4px">%s</div></td></tr>'
               % (G, F, GOLD, e(_span(rep, long=True))))
    # The headline and the summary.
    if note.get("headline"):
        row('<div style="font-size:20px;line-height:1.35;font-weight:700;color:%s">%s</div>'
            % (INK, e(note["headline"])), "26px 32px 0")
    if note.get("summary"):
        row('<p style="margin:10px 0 0;font-size:15px;line-height:1.65;color:%s">%s</p>'
            % (INK, e(note["summary"])))
    # At a glance: four numbers, two by two (holds on a phone).
    tiles = [(n.get("versions"), "versions of Jarvis shipped"),
             (n.get("events_banked"), "events banked"),
             (n.get("calls_people"), "calls checked by people"),
             (n.get("procedures"), "procedures at the bench")]

    def tile(v, words):
        return ('<td width="50%%" valign="top" style="padding:6px">'
                '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" '
                'style="background:%s;border:1px solid %s;border-radius:8px"><tr><td style="padding:14px 16px;%s">'
                '<div style="font-size:26px;font-weight:700;color:%s;line-height:1.1">%s</div>'
                '<div style="font-size:13px;color:%s;margin-top:4px">%s</div></td></tr></table></td>'
                % (PAPER, LINE, F, G, _n(v), SOFT, e(words)))
    row('<table role="presentation" width="100%%" cellpadding="0" cellspacing="0">'
        '<tr>%s%s</tr><tr>%s%s</tr></table>' % (tile(*tiles[0]), tile(*tiles[1]), tile(*tiles[2]),
                                                 tile(*tiles[3])), "20px 26px 0")
    # The week, in sections.
    for title, k in (("Progress", "progress"), ("At the bench", "bench"), ("The data", "data"),
                     ("Next", "next"), ("Keeping an eye on", "watch")):
        items = note.get(k) or []
        if items:
            row(heading(title) + bullets(items), "24px 32px 0")
    # The bench, as the sheet has it.
    evs = (rep.get("bench") or {}).get("events") or []
    if evs:
        th = ('<td style="padding:7px 8px;%sfont-size:11px;font-weight:700;letter-spacing:.06em;'
              'text-transform:uppercase;color:%s;border-bottom:2px solid %s">%%s</td>' % (F, SOFT, LINE))
        td = '<td style="padding:7px 8px;%sfont-size:13px;color:%s;border-bottom:1px solid %s">%%s</td>' % (F, INK, LINE)
        body = "".join("<tr>%s</tr>" % "".join(td % e(x) for x in (
            datetime.fromisoformat(v["day"]).strftime("%a %b ") + str(int(v["day"][8:])),
            v["what"], v["mouse"], v["lead"] or "")) for v in evs[:20])
        more = ('<div style="%sfont-size:12px;color:%s;margin-top:6px">and %d more on the sheet</div>'
                % (F, FAINT, len(evs) - 20)) if len(evs) > 20 else ""
        row(heading("The lab sheet this week") +
            '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0">'
            '<tr>%s</tr>%s</table>%s' % ("".join(th % h for h in ("Day", "Procedure", "Mouse", "Led by")),
                                         body, more), "24px 32px 0")
    # Every version shipped.
    vs = rep.get("versions") or []
    if vs:
        lines = "".join('<tr><td valign="top" style="padding:4px 10px 4px 0;%sfont-size:12px;color:%s;'
                        'white-space:nowrap">v%s</td><td style="padding:4px 0;%sfont-size:13px;color:%s;'
                        'line-height:1.45">%s</td></tr>' % (F, FAINT, e(v["v"]), F, INK, e(v["title"]))
                        for v in vs)
        row(heading("Every version this week (%d)" % len(vs)) +
            '<table role="presentation" cellpadding="0" cellspacing="0">%s</table>' % lines, "24px 32px 0")
    # The full numbers.
    nums = [("Versions of Jarvis shipped", n.get("versions")), ("Commits", n.get("commits")),
            ("Lines of code added", n.get("lines_added")), ("Lines of code removed", n.get("lines_removed")),
            ("Files changed", n.get("files")), ("Events banked", n.get("events_banked")),
            ("New bank entries", n.get("entries_banked")), ("New versions of banked entries", n.get("bank_versions")),
            ("Calls checked by people", n.get("calls_people")), ("Calls made by models", n.get("calls_models")),
            ("Procedures on the lab sheet", n.get("procedures")), ("New recordings", n.get("recordings_new"))]
    trs = "".join('<tr style="background:%s"><td style="padding:7px 10px;%sfont-size:13px;color:%s">%s</td>'
                  '<td style="padding:7px 10px;%sfont-size:13px;color:%s;text-align:right;font-weight:700">%s'
                  '</td></tr>' % (PAPER if i % 2 == 0 else "#ffffff", F, SOFT, e(k), F, INK, _n(v))
                  for i, (k, v) in enumerate((k, v) for k, v in nums if v is not None))
    row(heading("By the numbers") + '<table role="presentation" width="100%%" cellpadding="0" '
        'cellspacing="0" style="border:1px solid %s;border-radius:6px">%s</table>' % (LINE, trs),
        "24px 32px 0")
    # Who wrote it, and where it came from.
    if rep.get("writer") == NAME:
        who = ("Written by Hater of AI, Jarvis&rsquo;s helper, from the lab&rsquo;s own records: the "
               "code and its patch notes, the Event Bank, the curation sets and the Lab Operations sheet.")
    else:
        who = ("Written by Jarvis from the numbers in the lab&rsquo;s records, because %s."
               % e(why_words(rep.get("why_plain")) or "Hater of AI could not be asked this time"))
    out.append('<tr><td style="padding:26px 32px 28px;%s"><div style="border-top:1px solid %s;'
               'padding-top:14px;font-size:12px;line-height:1.6;color:%s">%s<br>Printed by %s on %s, '
               'and sent from the Barry Lab&rsquo;s account. '
               '<a href="%s" style="color:%s">Open the Lab Operations sheet</a>.</div></td></tr>'
               % (F, LINE, FAINT, who, e(rep.get("who") or "Jarvis"), e(rep.get("machine") or "a lab computer"),
                  e(SHEET_URL), G))
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
            '<body style="margin:0;padding:0;background:#e9efeb">'
            '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="background:#e9efeb">'
            '<tr><td align="center" style="padding:24px 12px">'
            '<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;'
            'width:100%%;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid %s">%s</table>'
            '</td></tr></table></body></html>' % (LINE, "".join(out)))


def check_mailer():
    """Whether the mailer answers and may send: (ok, words)."""
    cfg = mail_config()
    if not cfg.get("url"):
        return False, "no mailer is set up on this computer (%s)" % MAIL_CONFIG
    try:
        with urllib.request.urlopen(cfg["url"], timeout=60) as r:
            got = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:                               # noqa: BLE001
        return False, ("the mailer is not allowed to send yet (%s). Open %s as "
                       "barrylabuvm@gmail.com, choose authorize, Run, and Allow"
                       % (e, cfg.get("script") or "the Jarvis Mailer project"))
    return bool(got.get("ok")), "it may send %s more emails today" % got.get("quota")


def email(rep, who="lab"):
    """Send a printout to the lab list (or the test list) and note it on the
    printout. Returns what the mailer said; raises if it refused."""
    cfg = mail_config()
    to = cfg.get(who) or []
    if not cfg.get("url") or not cfg.get("secret"):
        raise RuntimeError("no mailer is set up on this computer (%s)" % MAIL_CONFIG)
    if not to:
        raise RuntimeError("nobody is on the %s list in %s" % (who, MAIL_CONFIG))
    body = {"kind": "weekly_email", "secret": cfg["secret"], "to": to,
            "subject": email_subject(rep), "text": as_text(rep), "html": email_html(rep)}
    req = urllib.request.Request(cfg["url"], data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "text/plain;charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("the mailer is not allowed to send yet: open %s as "
                               "barrylabuvm@gmail.com, choose authorize, Run, and Allow"
                               % (cfg.get("script") or "the Jarvis Mailer project"))
        raise RuntimeError("the mailer answered %s %s" % (e.code, e.reason))
    try:
        got = json.loads(text)
    except ValueError:
        raise RuntimeError("the mailer did not answer with JSON: %s"
                           % re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))[:300])
    # Its own kind, echoed, or it was some other web app answering.
    if got.get("kind") != "weekly_email":
        raise RuntimeError("that address is not the Jarvis Mailer")
    rep.setdefault("emailed", []).append({"at": _now_iso(), "list": who, "n": len(to),
                                          "ok": bool(got.get("ok")), "error": got.get("error"),
                                          "by": _hook("who")})
    # Noted on the printout only when it is this computer's own: no two
    # machines ever write the same file (GUI_logs/README.md).
    if rep.get("shard") == _shard():
        try:
            _save(rep)
        except OSError:
            pass
    if not got.get("ok"):
        raise RuntimeError("the mailer refused: %s" % got.get("error"))
    return got


def start():
    with _LOCK:
        if RUN["running"]:
            return RUN["id"]
        rid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        RUN.update(running=True, id=rid, steps=[], started=time.time(), stopped=False, proc=None)
    threading.Thread(target=_print, args=(rid,), daemon=True, name="jarvis-weekly-" + rid).start()
    return rid


def stop():
    with _LOCK:
        if not RUN["running"]:
            return False
        RUN["stopped"] = True
        proc = RUN["proc"]
    flossmod._kill(proc)
    return True


def reports(limit=12):
    out = []
    for p in _glob(REPORTS, ".json"):
        try:
            with open(p, encoding="utf-8") as fh:
                r = json.load(fh)
        except (OSError, ValueError):
            continue
        if r.get("status") != "printed":
            continue
        out.append({"id": r.get("id"), "shard": r.get("shard"), "at": r.get("at"),
                    "who": r.get("who"), "machine": r.get("machine"), "since": r.get("since"),
                    "until": r.get("until"), "writer": r.get("writer"),
                    "headline": (r.get("note") or {}).get("headline")})
    out.sort(key=lambda r: r.get("at") or "", reverse=True)
    return out[:limit]


def load(rid, shard=None):
    rid = os.path.basename(str(rid or ""))
    if shard:
        with open(_path(rid, os.path.basename(shard)), encoding="utf-8") as fh:
            return json.load(fh)
    for p in _glob(REPORTS, ".json"):
        if os.path.basename(p).startswith(rid + "@"):
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
    raise FileNotFoundError(rid)


def as_text(rep):
    """The printout as plain text: for Copy, for Results, and as the
    email's plain copy. Headed sections, so it reads well with no styling."""
    n, note = rep.get("numbers") or {}, rep.get("note") or {}
    rule = "-" * 60
    L = ["BARRY LAB  |  LAST 7 DAYS' WORK", _span(rep, long=True), rule, ""]
    if note.get("headline"):
        L += [note["headline"], ""]
    if note.get("summary"):
        L += [note["summary"], ""]
    L += ["AT A GLANCE",
          "  %s versions of Jarvis shipped   %s events banked" % (_n(n.get("versions")), _n(n.get("events_banked"))),
          "  %s calls checked by people     %s procedures at the bench" % (_n(n.get("calls_people")),
                                                                         _n(n.get("procedures"))), ""]
    for title, k in (("Progress", "progress"), ("At the bench", "bench"), ("The data", "data"),
                     ("Next", "next"), ("Keeping an eye on", "watch")):
        if note.get(k):
            L.append(title.upper())
            L += ["  * " + x for x in note[k]]
            L.append("")
    evs = (rep.get("bench") or {}).get("events") or []
    if evs:
        L.append("THE LAB SHEET THIS WEEK")
        L += ["  %s  %s, mouse %s%s" % (v["day"], v["what"], v["mouse"], ", led by " + v["lead"] if v["lead"] else "")
              for v in evs[:20]]
        if len(evs) > 20:
            L.append("  and %d more on the sheet" % (len(evs) - 20))
        L.append("")
    vs = rep.get("versions") or []
    if vs:
        L.append("EVERY VERSION THIS WEEK (%d)" % len(vs))
        L += ["  v%s  %s" % (v["v"], v["title"]) for v in vs]
        L.append("")
    L.append("BY THE NUMBERS")
    L.append("  %s versions shipped, %s commits, +%s / -%s lines in %s files"
             % (_n(n.get("versions")), _n(n.get("commits")), _n(n.get("lines_added")),
                _n(n.get("lines_removed")), _n(n.get("files"))))
    L.append("  %s events banked in %s new entries; %s new versions of banked entries"
             % (_n(n.get("events_banked")), _n(n.get("entries_banked")), _n(n.get("bank_versions"))))
    L.append("  %s calls checked by people, %s made by models" % (_n(n.get("calls_people")),
                                                               _n(n.get("calls_models"))))
    L.append("  %s procedures on the lab sheet; %s new recordings"
             % (_n(n.get("procedures")), _n(n.get("recordings_new"))))
    L += ["", rule]
    if rep.get("writer") == NAME:
        L.append("Written by Hater of AI from the lab's own records.")
    else:
        L.append("Written by Jarvis from the numbers, because %s."
                 % (why_words(rep.get("why_plain")) or "Hater of AI could not be asked this time"))
    L.append("Printed %s by %s on %s." % (rep.get("at", "")[:16].replace("T", " "),
                                          rep.get("who") or "someone", rep.get("machine") or "this computer"))
    L.append("Lab Operations sheet: " + SHEET_URL)
    return "\n".join(L)


def status():
    with _LOCK:
        run = {"running": RUN["running"], "id": RUN["id"], "steps": list(RUN["steps"][-12:]),
               "started": RUN["started"]}
    cfg = mail_config()
    return {"ok": True, "run": run, "reports": reports(), "sheet": SHEET_URL,
            "writer": {"engine": bool(flossmod.engine()), "key": bool(keymod.here()), "name": NAME},
            # Who it is emailed to is said as a count: the addresses stay on
            # the computer that sends.
            # The addresses go to this computer's own page only; they are
            # never written into GUI_logs or git.
            "mail": {"here": bool(cfg.get("url") and cfg.get("secret")),
                     "lab": len(cfg.get("lab") or []), "labTo": list(cfg.get("lab") or []),
                     "testTo": list(cfg.get("test") or []), "schedule": cfg.get("schedule")}}


def install(app, fail, who=None, machine=None, shard=None, reg=None, bank=None, curate=None,
            is_test=None, save=None):
    from flask import jsonify, request
    HOOKS.update(who=who, machine=machine, shard=shard, reg=reg, bank=bank, curate=curate,
                 is_test=is_test, save=save)
    # A printing the server died in the middle of is not left "printing".
    stale = time.time() - TIMEOUT_S - 300
    for p in _glob(REPORTS, "@%s.json" % _shard()):
        try:
            if os.path.getmtime(p) > stale:
                continue
            with open(p, encoding="utf-8") as fh:
                r = json.load(fh)
            if r.get("status") == "printing":
                r.update(status="failed", error="Jarvis stopped while it was printing")
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(r, fh, indent=1, ensure_ascii=False)
        except (OSError, ValueError):
            pass

    @app.route("/api/inside/week")
    def api_inside_week():
        return jsonify(status())

    @app.route("/api/inside/week/report")
    def api_inside_week_report():
        try:
            rep = load(request.args.get("id"), request.args.get("shard"))
        except (OSError, ValueError):
            return jsonify({"ok": False, "error": "no such printout on this computer"}), 404
        return jsonify({"ok": True, "report": rep, "text": as_text(rep),
                        "why": why_words(rep.get("why_plain"))})

    @app.route("/api/inside/week/print", methods=["POST"])
    def api_inside_week_print():
        try:
            rid = start()
        except Exception as e:                           # noqa: BLE001
            return fail("inside.week.print", e)
        return jsonify(dict(status(), id=rid))

    @app.route("/api/inside/week/stop", methods=["POST"])
    def api_inside_week_stop():
        stop()
        return jsonify(status())

    @app.route("/api/inside/week/email", methods=["POST"])
    def api_inside_week_email():
        """Email a printout: to the test list, or to the lab. The page asks
        for the lab only after the person has confirmed it."""
        b = request.get_json(silent=True) or {}
        who = "lab" if b.get("to") == "lab" else "test"
        try:
            rep = load(b.get("id"), b.get("shard"))
        except (OSError, ValueError):
            return jsonify({"ok": False, "error": "no such printout on this computer"}), 404
        try:
            got = email(rep, who)
        except Exception as e:                           # noqa: BLE001
            return jsonify({"ok": False, "error": str(e)}), 400
        feed.say("Last 7 days' work emailed to the %s list (%d)" % (who, got.get("sent", 0)),
                 kind="weekly", key="weekly-mail", done=True)
        return jsonify({"ok": True, "sent": got.get("sent"), "list": who})

    @app.route("/api/inside/week/save", methods=["POST"])
    def api_inside_week_save():
        b = request.get_json(silent=True) or {}
        try:
            rep = load(b.get("id"), b.get("shard"))
            name = "last-7-days-%s.txt" % (rep.get("until") or "")[:10]
            saved = HOOKS["save"](as_text(rep).encode("utf-8"), name)
        except FileNotFoundError:
            return jsonify({"ok": False, "error": "no such printout on this computer"}), 404
        except Exception as e:                           # noqa: BLE001
            return fail("inside.week.save", e)
        return jsonify({"ok": True, "saved": saved})
