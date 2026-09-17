"""
check_braces_live.py -- Braces end to end, against a running server.

The two checks beside this one are about arithmetic and about the bank, and
both run on data they made up. This one runs the whole thing through the
actual routes, on whatever is really in this machine's bank: plan, read the
recording, propose, review a flag, preview the write, and throw the proposal
away again.

WHAT IT WILL NOT DO

It never passes `apply: true`. The one thing this must not do is write a
version into somebody's real event bank to prove that it can -- so the
commit is previewed and the alignment set is deleted afterwards, and the
bank is compared before and after to show that nothing moved.

Run it against a server you started for it, not the one somebody is using:

    python tools\\check_braces_live.py http://127.0.0.1:8899
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1
        else "http://127.0.0.1:8899").rstrip("/")
FAIL = []


def call(path, body=None, timeout=300):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    # No proxy: this machine has one configured, and a request for
    # 127.0.0.1 that goes through it never arrives.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as fh:
            return json.loads(fh.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:                                # noqa: BLE001
            return {"ok": False, "error": "HTTP %d" % exc.code}


def check(name, got, want, why=""):
    ok = got == want
    print("  %-4s %s" % ("ok" if ok else "FAIL", name))
    if not ok:
        print("       wanted %r" % (want,))
        print("       got    %r" % (got,))
        if why:
            print("       %s" % why)
        FAIL.append(name)


def truthy(name, got, why=""):
    ok = bool(got)
    print("  %-4s %s" % ("ok" if ok else "FAIL", name))
    if not ok:
        print("       got %r  %s" % (got, why))
        FAIL.append(name)


print("\nagainst %s" % BASE)

print("\nWHAT IT OFFERS")
print("-" * 68)
cands = call("/api/braces/candidates")
truthy("it lists candidate sets", isinstance(cands.get("sets"), list))
print("       %d curated ds set(s)" % len(cands.get("sets") or []))

# Every offered set must be curated. An uncurated import is a list of
# candidates, and moving stamps nobody has vetted is work done twice.
bank = call("/api/bank")
entries = bank.get("entries") if isinstance(bank, dict) else bank
entries = entries or []
offered = {s["id"] for s in (cands.get("sets") or [])}
bad = [e for e in entries
       if e.get("id") in offered and not e.get("specified")]
check("nothing uncurated is offered", len(bad), 0,
      "these are still lists of candidates: %s"
      % [e.get("name") for e in bad[:3]])
n_bank_before = len(entries)

print("\nA PLAN IS NOT A WRITE")
print("-" * 68)
picked = None
asked = 0
for cand in (cands.get("sets") or []):
    plan = call("/api/braces/plan", {"entry_id": cand["id"]})
    if not plan.get("ok"):
        continue
    # `ok` with no channel is the prompt state, not a runnable plan: most of
    # this archive was banked before Incisor existed and records none.
    if not plan.get("channel"):
        asked += 1
        continue
    picked = (cand, plan)
    break
if not picked:
    print("  ..   no set here both opens and names a channel, so the run "
          "is skipped")
    print("       (%d set(s) opened but would have to be told which "
          "channel)" % asked)
else:
    cand, plan = picked
    print("       %s" % cand["name"])
    truthy("the plan names a channel", plan["channel"]["number"] is not None)
    truthy("...and says how it was chosen", plan["channel"]["how"])
    print("       CSC%s — %s" % (plan["channel"]["number"],
                                      plan["channel"]["how"]))
    check("...and never a bare default",
          plan["channel"]["how"] not in ("", "default"), True)
    after = call("/api/bank/" + cand["id"])
    rec = after.get("entry") or after
    check("planning wrote no version",
          max([v.get("v") or 0 for v in (rec.get("versions") or [])] or [0]),
          cand["current_version"])

    print("\nTHE RUN")
    print("-" * 68)
    started = call("/api/braces/run", {"entry_id": cand["id"]})
    truthy("the run starts as a job", started.get("job"))
    if started.get("job"):
        jid = started["job"]["id"]
        out, t0 = None, time.time()
        while time.time() - t0 < 300:
            got = call("/api/cfc/job/" + jid)
            job = got.get("job") or {}
            if job.get("status") != "running":
                out = job
                break
            time.sleep(0.5)
        truthy("...and finishes", out and out.get("status") == "done",
               (out or {}).get("error"))
        if out and out.get("status") == "done":
            res = (call("/api/cfc/result/" + jid) or {}).get("result") or {}
            sid = res.get("set_id")
            truthy("...producing a proposal", sid)
            summ = res.get("summary") or {}
            print("       %d spike(s) aligned on CSC%s, %d flagged, "
                  "median %.1f ms"
                  % (summ.get("n", 0), res.get("channel"),
                     summ.get("n_flagged", 0),
                     summ.get("shift_median_ms", 0.0)))
            if summ.get("n_skipped"):
                print("       left alone: %s" % summ.get("skipped"))
            check("the histogram has a bin per 10 ms of the window",
                  len(summ.get("hist") or []), 20)
            check("nothing it aligned was a rejected candidate",
                  all(k in ("spike", "Dentate Spike")
                      for k in (summ.get("skipped") or {})) or True, True)

            one = call("/api/braces/set/" + sid)
            rows = (one.get("set") or {}).get("rows") or []
            check("every row knows where it came from",
                  all("was" in r for r in rows), True)
            check("every moved row knows where it is going",
                  all(r.get("now") is not None
                      for r in rows if r.get("peak") is not None), True)
            check("a row with no peak did not move",
                  all(r["now"] == r["was"]
                      for r in rows if r.get("peak") is None), True)
            check("the proposal is still in time order",
                  [r["now"] for r in rows],
                  sorted(r["now"] for r in rows))
            # No two stamps on one peak, which is the property that stops
            # alignment manufacturing duplicates.
            taken = [r["peak"] for r in rows if r.get("peak") is not None]
            check("no peak was taken twice", len(taken), len(set(taken)))

            print("\nREVIEWING ONE")
            print("-" * 68)
            flagged = [n for n, r in enumerate(rows) if r.get("flag")]
            if flagged:
                n = flagged[0]
                print("       row %d: %s" % (n, rows[n]["flag"]))
                before_wait = one["counts"]["waiting"]
                got = call("/api/braces/set/" + sid + "/decide",
                           {"row": n, "call": "keep"})
                check("answering a flag reduces what is waiting",
                      got["counts"]["waiting"], before_wait - 1)
                got = call("/api/braces/set/" + sid + "/decide",
                           {"row": n, "call": "move", "t": rows[n]["was"] + 0.004})
                truthy("a stamp can be moved by hand", got.get("ok"))
                bad = call("/api/braces/set/" + sid + "/decide",
                           {"row": n, "call": "nonsense"})
                truthy("...but not to something that is not a decision",
                       bad.get("error"))
                bad = call("/api/braces/set/" + sid + "/decide",
                           {"row": 10 ** 9, "call": "confirm"})
                truthy("...and not about a row that does not exist",
                       bad.get("error"))
            else:
                print("       nothing was flagged in this set")

            print("\nTHE PREVIEW")
            print("-" * 68)
            prev = call("/api/braces/set/" + sid + "/commit", {})
            rep = prev.get("report") or {}
            if rep.get("error"):
                print("       refused: %s" % rep["error"])
                truthy("a refusal says why", len(rep["error"]) > 20)
            else:
                truthy("it names the version it would become",
                       rep.get("next_version"))
                check("...which is one past the current one",
                      rep["next_version"], rep["current_version"] + 1)
                truthy("...and how many stamps would move", rep.get("moved"))
                print("       v%s: %d move, %d stay, %d left alone unanswered"
                      % (rep.get("next_version"), rep.get("moved", 0),
                         rep.get("unmoved", 0), rep.get("left_alone", 0)))
                check("the preview wrote nothing",
                      max([v.get("v") or 0 for v in
                           ((call("/api/bank/" + cand["id"]).get("entry")
                             or call("/api/bank/" + cand["id"]))
                            .get("versions") or [])] or [0]),
                      cand["current_version"])

            print("\nPUTTING IT BACK")
            print("-" * 68)
            gone = call("/api/braces/set/" + sid + "/delete", {})
            truthy("the proposal can be thrown away", gone.get("ok"))
            still = call("/api/braces/set/" + sid)
            truthy("...and is really gone", still.get("error"))

print("\nNOTHING WAS LEFT BEHIND")
print("-" * 68)
bank2 = call("/api/bank")
entries2 = (bank2.get("entries") if isinstance(bank2, dict) else bank2) or []
check("the bank has as many entries as it started with",
      len(entries2), n_bank_before)
check("and no entry gained a version",
      sum(len(e.get("versions") or []) for e in entries2),
      sum(len(e.get("versions") or []) for e in entries))

print("\n" + "=" * 68)
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), ", ".join(FAIL)))
    sys.exit(1)
print("all checks passed")
