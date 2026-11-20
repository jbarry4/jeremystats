# -*- coding: utf-8 -*-
"""Print the last 7 days' work and email it, with no server and no page.

The weekly email is this, run by a scheduled task (tools/weekly_email.ps1)
on the computer that holds the mailer's settings
(%LOCALAPPDATA%\\Jarvis\\weekly\\mail.json). It prints the week exactly as
Inside Jarvis's printer does (backend/weekly.py: the commits, the patch
notes, the bank, the curation sets, the Lab Operations sheet, and Hater of
AI's note), keeps the printout in GUI_logs/weekly like any other, and sends
it from the lab's Google account through Jarvis Mailer (mailer/Code.js).

    python tools/weekly_email.py              print the week, email the lab list
    python tools/weekly_email.py --test       print the week, email the test list
    python tools/weekly_email.py --id ID      email a printout already made
    python tools/weekly_email.py --check      is the mailer up and allowed to send?

Each run adds a line to %LOCALAPPDATA%\\Jarvis\\weekly\\email.log.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import (curation, device as devicemod, eventbank, people,  # noqa: E402
                     profile as profilemod, sessreg, shards, store, weekly)
from backend.paths import LOGS_DIR  # noqa: E402

LOG = os.path.join(os.path.dirname(weekly.MAIL_CONFIG), "email.log")


def log(text):
    line = "%s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), text)
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def wire():
    """The hooks the server would give weekly.py, built the same way. The
    profile and the device are attached before anything reads, so a
    printout says who and which computer, not the git identity."""
    st = store.Store(LOGS_DIR, auto_stage=False)
    prof = profilemod.Profile(LOGS_DIR, st)
    st.profile = prof
    dev = devicemod.Device(LOGS_DIR, st)
    st.device = dev
    reg = sessreg.Registry(st)
    bank = eventbank.EventBank(LOGS_DIR, st)
    cur = curation.Curation(LOGS_DIR, st)

    def machine():
        try:
            return (dev.get(prof) or {}).get("name") or shards.machine_id()
        except Exception:                                # noqa: BLE001
            return shards.machine_id()

    weekly.HOOKS.update(who=lambda: (prof.effective() or {}).get("user"), machine=machine,
                        shard=shards.machine_id, reg=lambda: reg, bank=lambda: bank,
                        curate=lambda: cur, is_test=people.is_test_name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="email only the test list")
    ap.add_argument("--id", default="", help="email this printout instead of printing a new one")
    ap.add_argument("--check", action="store_true", help="only ask whether the mailer may send")
    a = ap.parse_args()

    ok, words = weekly.check_mailer()
    if a.check:
        log("check: " + ("ready, " if ok else "not ready: ") + words)
        return 0 if ok else 1
    if not ok:
        log("not sent: " + words)
        return 1

    wire()
    if a.id:
        rep = weekly.load(a.id)
        log("emailing printout %s" % a.id)
    else:
        log("printing the last 7 days")
        rep = weekly.print_now()
        if rep.get("status") != "printed":
            log("not sent: the printing %s (%s)" % (rep.get("status"), rep.get("error")))
            return 1
        log("printed %s, written by %s%s" % (rep["id"], rep.get("writer"),
                                             " (" + rep["why_plain"] + ")" if rep.get("why_plain") else ""))
    who = "test" if a.test else "lab"
    try:
        got = weekly.email(rep, who)
    except Exception as e:                               # noqa: BLE001
        log("not sent to the %s list: %s" % (who, e))
        return 1
    log("sent to the %s list (%d), %s more allowed today" % (who, got.get("sent", 0), got.get("quota")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
