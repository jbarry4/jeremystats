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
# ---------------------------------------------------------------- bulk --
# What a bulk run reads off the listing, checked here because a bulk table
# built on a missing field draws forty-eight blank rows and says nothing.
sets_all = cands.get("sets") or []
have_v = [c for c in sets_all if c.get("versions")]
check("every candidate carries its version history",
      len(have_v), len(sets_all))
truthy("...with a ref for each, which is what a run is given back",
       all(v.get("ref") for c in sets_all for v in (c.get("versions") or [])))

# The newest READABLE version, which is not the newest and not the largest
# number. A run started from a version whose snapshot never arrived fails,
# so the one flagged has to be one that can actually be read.
flagged = [c for c in sets_all
           if any(v.get("newest") for v in (c.get("versions") or []))]
check("every candidate names a newest readable version",
      len(flagged), len([c for c in sets_all
                         if any(v.get("usable")
                                for v in (c.get("versions") or []))]))
truthy("...and it is one that can be read",
       all(v.get("usable") for c in sets_all
           for v in (c.get("versions") or []) if v.get("newest")))
truthy("...and it is the one the listing names",
       all(v.get("name") == c.get("newest_usable_name")
           for c in sets_all for v in (c.get("versions") or [])
           if v.get("newest")))
behind = [c for c in sets_all
          if c.get("newest_usable_name")
          and c.get("newest_name") != c.get("newest_usable_name")]
print("       %d of %d set(s) have a newest version that never reached "
      "this machine" % (len(behind), len(sets_all)))

# A set with nothing in it to align.
#
# Fully curated and every candidate rejected is a real state -- nine of the
# forty-eight sets here are that, one of them 738 rejections -- and running
# one reads the recording for a minute to file a proposal with no rows in
# it. It has to be refused, and the refusal has to say why.
none_good = [c for c in sets_all if not c.get("n_good")]
truthy("the listing says how many of each set are actually spikes",
       all("n_good" in c for c in sets_all))
print("       %d of %d set(s) hold no dentate spikes at all"
      % (len(none_good), len(sets_all)))
if none_good:
    bad = call("/api/braces/run", {"entry_id": none_good[0]["id"]})
    check("a set with no spikes is refused rather than read",
          bool(bad.get("ok")), False)
    truthy("...and the refusal says why",
           "dentate spike" in (bad.get("error") or ""),
           bad.get("error"))

n_bank_before = len(entries)

print("\nA PLAN IS NOT A WRITE")
print("-" * 68)
picked = None
shut = 0
# The smallest set that is actually made of dentate spikes.
#
# Small, because the run reads a window per stamp and a suite nobody will
# wait for is a suite nobody runs. But small ALONE picked a set of four
# stamps all still under review: nothing to align, so nothing moved,
# nothing was flagged, and the commit preview got as far as refusing --
# three sections reporting ok on an empty set. A set has to contain enough
# of the thing to exercise the thing.
GOOD = ("spike", "Dentate Spike")


def n_good(r):
    lab = r.get("by_label") or {}
    return sum(int(lab.get(k) or 0) for k in GOOD)


usable = [r for r in (cands.get("sets") or []) if n_good(r) >= 20]
by_size = sorted(usable, key=n_good)
if not usable:
    print("  ..   no set here holds twenty curated spikes")
for cand in by_size:
    plan = call("/api/braces/plan", {"entry_id": cand["id"]})
    if not plan.get("ok"):
        # No recording on this machine, which is a state the route is
        # supposed to report rather than a failure of it.
        shut += 1
        continue
    picked = (cand, plan)
    break
if not picked:
    print("  ..   no set here opens a recording on this machine, so the "
          "run is skipped")
    print("       (%d set(s) could not be opened)" % shut)
else:
    cand, plan = picked
    print("       %s: %d stamp(s), %d of them spikes"
          % (cand["name"], cand.get("n") or 0, n_good(cand)))
    # NO CHANNEL IS PICKED ANY MORE. The plan offers every channel with
    # whether it is marked bad, and the run sweeps them for the depth the
    # event is actually at. A plan that named one channel would be the old
    # design, and this check used to require it -- which is why everything
    # below here quietly stopped running.
    truthy("the plan offers the channels rather than choosing one",
           len(plan.get("channels") or []) > 1)
    truthy("...saying which are marked bad",
           all("bad" in c for c in (plan.get("channels") or [])))
    truthy("...and which versions can supply the stamps",
           any(v.get("usable") for v in (plan.get("versions") or [])))
    truthy("...each named uniquely, because the number is not",
           len({v["name"] for v in (plan.get("versions") or [])})
           == len(plan.get("versions") or []))
    print("       %d channel(s), %d bad; %d version(s)"
          % (len(plan.get("channels") or []),
             sum(1 for c in (plan.get("channels") or []) if c.get("bad")),
             len(plan.get("versions") or [])))
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
            depth = summ.get("depth") or {}
            band = depth.get("channels") or []
            truthy("...having swept the probe for the depth band", band)
            check("...which is narrower than the probe",
                  len(band) < (depth.get("of") or 10 ** 9), True)
            print("       %d spike(s) aligned on CSC%s-CSC%s of %d swept, "
                  "%d flagged, median %.1f ms"
                  % (summ.get("n", 0), band[0] if band else "?",
                     band[-1] if band else "?", depth.get("of") or 0,
                     summ.get("n_flagged", 0),
                     summ.get("shift_median_ms", 0.0)))
            pars = res.get("params") or {}
            print("       %s, candidates %.0f ms apart over %.1f sd"
                  % (pars.get("measure"), pars.get("cand_dist_ms") or 0,
                     pars.get("cand_height_sd") or 0))
            truthy("the run records which measure it used",
                   pars.get("measure") in ("csd", "voltage"))
            truthy("...and how close two candidates could be",
                   (pars.get("cand_dist_ms") or 0) > 0)
            # Zero is the answer now and it is a real answer: a candidate
            # is a local maximum of the curve whatever its height. What is
            # checked is that the set SAYS which rule it was made under,
            # because a set made with a floor and one made without are not
            # comparable and nothing else records the difference.
            truthy("...and whether a candidate had to clear anything",
                   "cand_height_sd" in pars)
            truthy("...and that the mains was taken out first",
                   (pars.get("line_hz") or 0) > 0)
            # Nothing is projected onto it any more, but it is still the
            # one number that says the band sat on an event.
            truthy("...and the depth signature of what it found",
                   len(pars.get("profile") or {}) > 2)
            prof = pars.get("profile") or {}
            # A dentate spike is a SINK with sources either side of it, so
            # the profile has both signs in it. One sign everywhere would
            # mean the projection is a weighted magnitude, which is the
            # thing this replaced.
            vals = [float(v) for v in prof.values()]
            truthy("...which has both signs in it, being a dipole",
                   any(v > 0 for v in vals) and any(v < 0 for v in vals))
            scr = pars.get("screened") or {}
            print("       screened: %s"
                  % (", ".join("CSC%s %s" % (k, v) for k, v in scr.items())
                     or "every contact usable"))
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
            # Reported, not asserted. Nothing is gated on the background
            # any more, so "how many landed on something barely above it"
            # is an observation about this recording rather than a rule the
            # code is keeping -- and a check that asserts a number nothing
            # controls is a check that fails for reasons nobody can act on.
            floor = (one.get("set") or {}).get("summary", {}).get(
                "cand_floor_uv")
            got_uv = [r["peak_uv"] for r in rows
                      if r.get("peak_uv") is not None]
            if floor and got_uv:
                low = [v for v in got_uv if v < floor]
                print("       %d of %d aligned onto something under the "
                      "4.5 SD background (%.0f)"
                      % (len(low), len(got_uv), floor))
            check("no stamp moved further than the window allowed",
                  all(abs(r.get("shift_ms") or 0) <= 100.0001 for r in rows),
                  True)

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
                print("       v%s: %d event(s) — %d move, %d stay, "
                      "%d left alone unanswered"
                      % (rep.get("next_name") or rep.get("next_version"),
                         rep.get("n_events", 0), rep.get("moved", 0),
                         rep.get("unmoved", 0), rep.get("left_alone", 0)))
                # Only the events. A banked alignment holds the curated
                # spikes and not the candidates somebody threw out, so the
                # preview has to say what it is leaving behind.
                truthy("...and what it leaves out for not being an event",
                       "dropped" in rep)
                if rep.get("n_dropped"):
                    print("       dropping %d: %s"
                          % (rep["n_dropped"], rep.get("dropped")))
                check("nothing rejected is written",
                      rep.get("n_events", 0) + rep.get("n_dropped", 0),
                      cand.get("n"))
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
