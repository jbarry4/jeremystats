# -*- coding: utf-8 -*-
"""The PI's practice layer (backend/pisafe.py).

    python tools/test_pisafe.py

Everything here happens in a temp folder standing in for GUI_logs; no
request leaves the computer (the shared database is pointed at a closed
port, and only its write path is exercised, which the layer answers
itself). Checks:

  1. who counts as the PI
  2. a record changed in the layer: the real shard is byte-for-byte the same,
     the layer shows the change, the real view does not
  3. deleting in the layer hides, and deletes nothing real
  4. read_mine records (the profile) start from the real one
  5. preferences: screen-shaped local keys carry into the layer
  6. day logs: the layer's lines are its own
  7. start-up: the real profile turns it on; a profile saved in the layer
     cannot turn it off; 14 days throws it away
  8. revert: every layer file goes, the real records read as before
  9. the routes held, the shared database not written, the cluster not asked
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import cloud as cloudmod, pisafe, shards, store as storemod, vacc  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-70s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


def raw(path):
    with open(path, "rb") as fh:
        return fh.read()


def main():
    os.environ.pop("Jarvis_PISAFE", None)
    tmp = tempfile.mkdtemp(prefix="jarvis_pisafe_")
    logs = os.path.join(tmp, "GUI_logs")
    sd = pisafe.state_dir(logs)
    me = shards.real_machine_id()
    try:
        print("\n1. who counts as the PI")
        check("the name, any case and spacing",
              pisafe.matches({"name": "  jeremy   BARRY "}))
        check("the role PI", pisafe.matches({"name": "x", "role": "P.I."}))
        check("Principal Investigator", pisafe.matches({"role": "Principal investigator"}))
        check("his UVM email", pisafe.matches({"email": "JBarry4@uvm.edu"}))
        check("not a student", not pisafe.matches(
            {"name": "Shahriar Tafti", "role": "Grad student", "email": "s@uvm.edu"}))
        check("not an empty profile", not pisafe.matches({}))

        print("\n2. a record changed in the layer")
        shards.configure_safe(False, sd)
        book = shards.Book(os.path.join(logs, "sessions"), {"paths": shards.UNION})
        book.write("m1", {"note": "real", "paths": ["D:/a"]})
        book.write("m2", {"note": "two"})
        real_m1 = book.real_path("m1")
        before = raw(real_m1)
        shards.configure_safe(True, sd)
        rec = book.read("m1")
        check("the layer reads the real record to begin with",
              rec and rec.get("note") == "real", rec)
        rec["note"] = "the PI's"
        rec["paths"] = rec["paths"] + ["E:/b"]
        book.write("m1", rec)
        check("the real shard is byte-for-byte the same", raw(real_m1) == before)
        check("the change went to the layer's own file",
              os.path.isfile(book.mine("m1")) and "@pisafe-" in book.mine("m1"))
        got = book.read("m1")
        check("the layer shows it", got.get("note") == "the PI's"
              and sorted(got.get("paths")) == ["D:/a", "E:/b"], got)
        check("all() shows it too", any(r.get("note") == "the PI's" for r in book.all()))
        with shards.real_view():
            got = book.read("m1")
            check("the real view does not", got.get("note") == "real"
                  and got.get("paths") == ["D:/a"], got)
            check("and writes there go to the real name",
                  shards.machine_id() == me)
        check("back in the layer afterwards", shards.machine_id() == shards.SAFE_PREFIX + me)

        print("\n3. deleting in the layer hides")
        book.erase("m2")
        check("the record is gone from the layer", book.read("m2") is None
              and "m2" not in book.bases())
        check("its real file is still on disk", os.path.isfile(book.real_path("m2")))
        with shards.real_view():
            check("and the real view still has it",
                  (book.read("m2") or {}).get("note") == "two")
        book.write("m2", {"note": "made again"})
        check("made again in the layer, it is only the new one",
              (book.read("m2") or {}).get("note") == "made again")
        book.write("m3", {"note": "three"})
        shards.configure_safe(False, sd)
        book.write("m4", {"note": "four"})
        shards.configure_safe(True, sd)
        book.forget("m4")
        check("forget hides this machine's real shard",
              book.read("m4") is None and os.path.isfile(book.real_path("m4")))
        n = book.erase_if("m1", lambda s: True)
        check("erase_if hides real shards and drops the layer's",
              n == 2 and book.read("m1") is None and os.path.isfile(real_m1)
              and not os.path.isfile(book.mine("m1")), n)

        print("\n4. a record read with read_mine (the profile)")
        shards.configure_safe(False, sd)
        prefs = shards.Book(os.path.join(logs, "prefs"), {})
        prefs.write("profile", {"name": "Jeremy Barry", "email": "jbarry4@uvm.edu"})
        real_prof = raw(prefs.real_path("profile"))
        shards.configure_safe(True, sd)
        check("the layer starts from the real one",
              prefs.read_mine("profile").get("name") == "Jeremy Barry")
        prefs.write("profile", dict(prefs.read_mine("profile"), name="Someone Else"))
        check("a change is the layer's", prefs.read_mine("profile").get("name") == "Someone Else")
        check("its other fields came with it",
              prefs.read_mine("profile").get("email") == "jbarry4@uvm.edu")
        check("the real profile is untouched", raw(prefs.real_path("profile")) == real_prof)

        print("\n5. preferences")
        shards.configure_safe(False, sd)
        st = storemod.Store(logs, auto_stage=False)
        st.set_prefs({"theme": "dark", "favorites": ["a.py"], "lab_note": "real"})
        real_wb = raw(st.prefs.real_path(storemod.PREFS_BASE))
        shards.configure_safe(True, sd)
        got = st.get_prefs()
        check("a local key reads through from the real shard", got.get("theme") == "dark", got)
        st.set_prefs({"lab_note": "the PI's"})
        got = st.get_prefs()
        check("a change shows, and the local key is still there",
              got.get("lab_note") == "the PI's" and got.get("theme") == "dark", got)
        check("the real workbench is untouched",
              raw(st.prefs.real_path(storemod.PREFS_BASE)) == real_wb)
        with shards.real_view():
            check("the real view still says real", st.get_prefs().get("lab_note") == "real")

        print("\n6. day logs")
        log = shards.DayLog(os.path.join(logs, "activity"))
        shards.configure_safe(False, sd)
        log.append({"at": "2026-11-20T10:00:00", "action": "real"})
        shards.configure_safe(True, sd)
        log.append({"at": "2026-11-20T11:00:00", "action": "pi"})
        acts = [r["action"] for r in log.read(day="2026-11-20")]
        check("the layer sees both lines", sorted(acts) == ["pi", "real"], acts)
        with shards.real_view():
            acts = [r["action"] for r in log.read(day="2026-11-20")]
            check("the real view sees only the real one", acts == ["real"], acts)

        print("\n7. start-up")
        shards.configure_safe(False, sd)
        check("decide reads the REAL profile: on", pisafe.decide(logs) is True)
        check("and wrote when it began", os.path.isfile(os.path.join(sd, "started.json")))
        check("the layer's 'Someone Else' did not turn it off", shards.safe_on())
        os.environ["Jarvis_PISAFE"] = "0"
        check("Jarvis_PISAFE=0 forces it off", pisafe.decide(logs) is False)
        os.environ.pop("Jarvis_PISAFE")
        pisafe.decide(logs)
        s = pisafe.status(logs)
        check("status counts the layer's files", s["on"] and s["files"] >= 5
              and s["hidden"] >= 3, s)

        print("\n8. revert")
        layer = [p for p in pisafe._layer_files(logs)]
        got = pisafe.revert(logs)
        check("every layer file removed", got["removed"] == len(layer)
              and not got["failed"], got)
        check("none left anywhere", not pisafe._layer_files(logs))
        check("still on afterwards", shards.safe_on())
        check("m1 reads as it did before", (book.read("m1") or {}).get("note") == "real")
        check("m2 is back", (book.read("m2") or {}).get("note") == "two")
        check("m4 is back", (book.read("m4") or {}).get("note") == "four")
        check("m3 never existed", book.read("m3") is None)
        check("the profile is his again", prefs.read_mine("profile").get("name") == "Jeremy Barry")
        check("the workbench is the real one", st.get_prefs().get("lab_note") == "real")
        check("the real files are all still there",
              raw(real_m1) == before and raw(prefs.real_path("profile")) == real_prof)

        book.write("m1", dict(book.read("m1"), note="later"))
        old = (datetime.now(timezone.utc) - timedelta(days=pisafe.KEEP_DAYS + 1)).isoformat()
        shards.write_json_atomic(os.path.join(sd, "started.json"), {"at": old})
        pisafe.decide(logs)
        check("a layer older than %d days is thrown away at start-up" % pisafe.KEEP_DAYS,
              (book.read("m1") or {}).get("note") == "real" and not pisafe._layer_files(logs))

        print("\n9. what leaves the computer")
        check("a VACC upload is held", pisafe.held("/api/vacc/upload", "POST"))
        check("a monolith run is held", pisafe.held("/api/arc/monolith/run", "POST"))
        check("a circuit batch run is held", pisafe.held("/api/arc/circuit/batch/run", "POST"))
        check("the weekly email is held", pisafe.held("/api/inside/week/email", "POST"))
        check("the lab sheet is not written", pisafe.held("/api/vos/apply", "POST"))
        check("looking is not held", not pisafe.held("/api/vacc/upload", "GET"))
        check("saving a preference is not held (the layer has it)",
              not pisafe.held("/api/prefs", "POST"))
        c = cloudmod.Cloud(logs)
        c.cfg = {"url": "http://127.0.0.1:9", "key": "x"}
        try:
            n = c.upsert("sessions", [{"gid": "g1"}, {"gid": "g2"}], on_conflict="gid")
            back = c.upsert_returning("presence", {"gid": "g1", "who": "pi"})
            c.patch_rows("sessions", "gid=eq.g1", {"retired": True})
            c.delete("sessions", "gid=eq.g1")
            ok = n == 2 and back == {"gid": "g1", "who": "pi"}
            check("the shared database is answered here, not written", ok, (n, back))
        except Exception as exc:                         # noqa: BLE001
            check("the shared database is answered here, not written", False, exc)
        check("and the cloud client is still this machine by its real name",
              c.machine == me)
        try:
            vacc._hold_outward("cd x; sbatch --parsable submit.sh")
            check("sbatch is refused", False)
        except vacc.SSHError:
            check("sbatch is refused", True)
        try:
            vacc._hold_outward("ls -la", stdin=b"import os\nprint(1)\n")
            check("a read is not", True)
        except vacc.SSHError as exc:
            check("a read is not", False, exc)
        try:
            pisafe.refuse_outward("The upload")
            check("an upload is refused", False)
        except pisafe.Held:
            check("an upload is refused", True)

        shards.configure_safe(False, sd)
        check("off: nothing is held", not pisafe.held("/api/vacc/upload", "POST"))
        try:
            vacc._hold_outward("sbatch x")
            check("off: the cluster may be asked", True)
        except vacc.SSHError:
            check("off: the cluster may be asked", False)
    finally:
        shards.configure_safe(False)
        os.environ.pop("Jarvis_PISAFE", None)
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%s" % ("FAILED: %d" % len(FAILED) if FAILED else "all passed"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
