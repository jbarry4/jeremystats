"""The DS-type ML program (2026-11-20), out of the Jarvis process (the new
engine code is pushed to the VACC with each run). Makes the runs in order,
submits each when the queue has room (the account takes 1000 jobs), brings
answers home, resubmits failed tasks once, and writes each leaderboard.
State in er2_types_state.json; safe to restart (it picks up where it was).

  python er2_types_driver.py
"""
import json
import os
import sys
import time

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
from backend import vacc, er2run as R  # noqa: E402
from backend.er2 import engine as E, typed as TY  # noqa: E402

S = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(S, "er2_types_state.json")
QUEUE_CAP = 950
SETS = {"Halo": 5, "Strict": 6}


def plan():
    out = []
    for nm, av in SETS.items():
        out += [
            {"name": "%s · DS1 vs DS2" % nm, "amber": av, "tasks": TY.grid_type12(), "explain": True, "drop": True, "part": "general", "time": "12:00:00"},
            {"name": "%s · DS1 minus DS2 per mouse" % nm, "amber": av, "tasks": TY.grid_contrast(E.TARGETS, E.MODELS), "explain": True, "drop": True,
             "part": "general", "time": "12:00:00"},
            {"name": "%s · one DS type at a time" % nm, "amber": av, "tasks": TY.grid_types(E.TARGETS, E.MODELS), "explain": True, "drop": False,
             "part": "general", "time": "12:00:00"},
            {"name": "%s · random twins (yardstick)" % nm, "amber": av, "tasks": TY.grid_types(E.TARGETS, E.MODELS, subsets=TY.TWINS),
             "explain": False, "drop": False, "part": "short", "time": "03:00:00"},
        ]
    for nm, av in SETS.items():
        out.append({"name": "%s · all events, with the raw event" % nm, "amber": av, "tasks": E.grid(E.TARGETS, E.VIEWS + ("raw",), E.MODELS),
                    "explain": True, "drop": True, "part": "general", "time": "12:00:00"})
    return out


def say(*a):
    print(time.strftime("%m-%d %H:%M"), *a, flush=True)


def queued(r):
    try:
        return int((r("bash -c %s" % vacc.q("squeue -u sakhava1 -h -r | wc -l"), timeout=120) or "0").strip().splitlines()[-1])
    except Exception:                                      # noqa: BLE001
        return 10 ** 6


st = json.load(open(STATE)) if os.path.exists(STATE) else {"runs": []}
P = plan()
cfg = vacc.load_config(os.path.join(APP, "GUI_logs"))
r = vacc._runner(cfg)
say("plan:", ["%s (%d)" % (p["name"], len(p["tasks"])) for p in P], "total", sum(len(p["tasks"]) for p in P))
while True:
    done_names = {x["name"] for x in st["runs"]}
    # submit the next run when it fits
    for p in P:
        if p["name"] in done_names:
            continue
        q = queued(r)
        if q + len(p["tasks"]) > QUEUE_CAP:
            break
        run = R.new_run(tasks=p["tasks"], amber_version=p["amber"], where="vacc", explain=p["explain"], drop=p["drop"],
                        note="DS-type program 2026-11-20: " + p["name"])
        run.update(partition=p["part"], time_limit=p["time"])
        R.save_run(run)
        R.submit_vacc(cfg, run["rid"], APP)
        st["runs"].append({"name": p["name"], "rid": run["rid"], "n": run["n"], "resubmitted": False, "done": False})
        json.dump(st, open(STATE, "w"), indent=1)
        say("submitted", run["rid"], p["name"], run["n"], "tasks; queue was", q)
        done_names.add(p["name"])
    # follow
    for x in st["runs"]:
        if x["done"]:
            continue
        try:
            f = R.fetch_vacc(cfg, x["rid"])
            pol = R.poll_vacc(cfg, x["rid"])
        except Exception as exc:                           # noqa: BLE001
            say("retry", x["rid"], exc)
            continue
        tally = pol.get("tally") or {}
        line = "%s %s: %d/%d answered %s" % (x["rid"], x["name"], f["answered"], f["n"], tally)
        if line != x.get("last"):
            say(line)
            x["last"] = line
        if f["answered"] >= f["n"]:
            R.leaderboard(x["rid"])
            x["done"] = True
            say("DONE", x["rid"], x["name"])
        elif not pol.get("active") and tally.get("running", 0) == 0 and tally.get("queued", 0) == 0:
            have = set(R.answered(x["rid"]))
            miss = [t["i"] for t in R.read_run(x["rid"])["tasks"] if t["i"] not in have]
            if miss and not x["resubmitted"]:
                R.resubmit_vacc(cfg, x["rid"], APP, miss)
                x["resubmitted"] = True
                say("resubmitted", len(miss), "tasks of", x["rid"])
            elif miss:
                R.leaderboard(x["rid"])
                x["done"] = True
                say("DONE WITH GAPS", x["rid"], x["name"], "missing", len(miss))
        json.dump(st, open(STATE, "w"), indent=1)
    if len(st["runs"]) == len(P) and all(x["done"] for x in st["runs"]):
        say("ALL RUNS DONE")
        break
    time.sleep(300)
