# -*- coding: utf-8 -*-
"""Notes, Save, View only's server half, and hiding copies (2026-11-20).
Offline, against a throwaway bank and curation store.

    python tools/test_curation_tools.py

What is guarded:

  * a note on a candidate changes nothing but the note, and goes into the
    bank with the event when the set is banked; a set started again from
    that version has it back;
  * opening a set puts nobody's name on it; the first decision does;
  * a set started from (or put back to) a version where every event is
    already decided never banks itself -- Rain's "pull up old shit and it
    saves a new version";
  * "Keep only this one" hides the other sets of the same step on the same
    recording, and nothing else; a version's keep_only hides every other
    version of the entry;
  * a note on a Braces/Lock/Eye row travels into the aligned version;
  * the sync carries notes on their own clock and never lets a note move a
    label; Save sends one set and reads it back, and in the PI's practice
    layer looks done without sending;
  * W is a reserved key, so no added category can take it.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

FAILED = []


def check(name, ok, detail=""):
    print("  %-72s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:600])
    if not ok:
        FAILED.append(name)


class FakeCloud:
    """Just enough of backend.cloud.Cloud for a Save: what was upserted, and
    counts answered from it."""
    configured = True

    def __init__(self):
        self.rows = {}

    def upsert(self, table, rows, on_conflict=None):
        self.rows.setdefault(table, []).extend(rows)
        return len(rows)

    def count(self, table, query=""):
        rows = self.rows.get(table) or []
        sid = query.split("set_id=eq.")[1].split("&")[0]
        rows = [r for r in rows if r.get("set_id") == sid]
        if "label=neq.unspecified" in query:
            rows = [r for r in rows if r.get("label") != "unspecified"]
        return len(rows)


def main():
    from backend import app as A                         # noqa: E402
    from backend import curation as C, eventbank as EB   # noqa: E402
    from backend import bracesset as BS, shards          # noqa: E402

    tmp = tempfile.mkdtemp(prefix="jarvis-curation-tools-")
    saved = (A.BANK, A.CURATE, A.BRACES, A.STORE.record_activity,
             A.mirror_bank_soon, A._session_by_gid, A.CLOUD.cloud,
             A.CLOUD.curate)
    try:
        A.BANK = EB.EventBank(tmp, A.STORE)
        A.CURATE = C.Curation(tmp, A.STORE)
        A.BRACES = BS.BracesSets(tmp, A.STORE)
        A.STORE.record_activity = lambda *a, **k: None
        A.mirror_bank_soon = lambda: None
        real = saved[5]
        # Project, mouse and session as the entries say, or a bank written
        # through a route files the entry under a second name.
        A._session_by_gid = lambda gid: ({"gid": gid, "label": gid + " label",
                                          "here": [], "project": "TEST",
                                          "mouse": 1, "session": 2}
                                         if str(gid).startswith("g")
                                         else real(gid))
        A.CLOUD.curate = A.CURATE
        cli = A.app.test_client()
        me = (A.STORE.provenance() or {}).get("user")

        ent = A.BANK.add({
            "gid": "g1", "type": "pooled", "name": "g1 pool",
            "session_label": "g1 label", "project": "TEST", "mouse": 1,
            "session": 2, "pipeline": "The Confluence: test",
            "added_by": "tools-test",
            "events": [{"start": 1.0 + i, "channel": 3, "origin": "incisor"}
                       for i in range(4)]})

        # ---- opening claims nothing; the first decision does ----
        r = cli.post("/api/curation/from-bank", json={
            "gid": "g1", "kind": "pooled", "entry": ent["id"],
            "version": 0}).get_json()
        sk = r.get("kind")
        check("a set is made from v0", r.get("ok") and sk, r)
        cli.post("/api/curation/g1/%s/open" % sk, json={"open": True})
        rec = A.CURATE.get("g1", sk)
        check("opening it puts nobody's name on it", not rec.get("assignee"),
              rec.get("assignee"))
        check("a v0 set may still bank itself once", not rec.get("autobanked"))
        ids = [e["id"] for e in rec["events"]]

        # ---- a note changes nothing but the note ----
        cli.post("/api/curation/g1/%s/label" % sk,
                 json={"event": ids[0], "label": "flag"})
        rec = A.CURATE.get("g1", sk)
        check("the first decision makes the set this person's",
              rec.get("assignee") == me, (rec.get("assignee"), me))
        got = cli.post("/api/curation/g1/%s/note" % sk, json={
            "event": ids[0], "note": "  two spikes on top of each other  "})
        j = got.get_json()
        ev = next(e for e in A.CURATE.get("g1", sk)["events"]
                  if e["id"] == ids[0])
        check("the note is kept, trimmed", j.get("ok")
              and ev.get("note") == "two spikes on top of each other", j)
        check("with who and when", ev.get("note_by") == me and ev.get("note_at"))
        check("and the label is untouched", ev.get("label") == "flag")
        bad = cli.post("/api/curation/g1/%s/note" % sk,
                       json={"event": "nope", "note": "x"})
        check("a note on a candidate that is not there is refused",
              bad.status_code == 400)

        # ---- banked with the event, and back in a set made from it ----
        for i in ids[1:]:
            cli.post("/api/curation/g1/%s/label" % sk,
                     json={"event": i, "label": "spike"})
        b = cli.post("/api/curation/g1/%s/bank" % sk, json={"note": "test"})
        check("the set banks", b.status_code == 200 and b.get_json().get("ok"),
              b.get_json())
        e2 = A.BANK.get(ent["id"])
        noted = [e for e in e2.get("events") or [] if e.get("note")]
        check("the note went into the bank with its event",
              len(noted) == 1 and abs(noted[0]["start"] - 1.0) < 1e-9
              and noted[0].get("note_by") == me, noted)

        # A set started from that finished version: never banks itself.
        A.CURATE.delete("g1", sk)
        newest = max(e2["versions"], key=lambda v: v.get("v") or 0)
        r2 = cli.post("/api/curation/from-bank", json={
            "gid": "g1", "kind": "pooled", "entry": ent["id"],
            "version": newest.get("id") or newest.get("v")}).get_json()
        rec2 = A.CURATE.get("g1", r2.get("kind"))
        check("a set from a finished version is marked as banked already",
              bool((rec2 or {}).get("autobanked")), rec2 and rec2.get("autobanked"))
        auto = cli.post("/api/curation/g1/%s/bank" % r2["kind"],
                        json={"auto": True, "note": "Every event decided"})
        check("so changing a call in it does not bank a new version",
              (auto.get_json() or {}).get("skipped"), auto.get_json())
        ev2 = next((e for e in rec2["events"]
                    if abs(e["start"] - 1.0) < 1e-9), {})
        check("and its note is back on the event", ev2.get("note")
              == "two spikes on top of each other", ev2)

        # ---- clearing a note ----
        cli.post("/api/curation/g1/%s/note" % r2["kind"],
                 json={"event": ev2["id"], "note": ""})
        ev3 = next(e for e in A.CURATE.get("g1", r2["kind"])["events"]
                   if e["id"] == ev2["id"])
        check("a cleared note is gone, its time kept",
              "note" not in ev3 and ev3.get("note_at"), ev3)

        # ---- keep only this one: sets ----
        ent_b = A.BANK.add({
            "gid": "g1", "type": "pooled", "name": "g1 pool B",
            "session_label": "g1 label", "project": "TEST", "mouse": 1,
            "session": 2, "pipeline": "The Confluence: test",
            "added_by": "tools-test",
            "events": [{"start": 9.0, "channel": 3}]})
        rb = cli.post("/api/curation/from-bank", json={
            "gid": "g1", "kind": "pooled", "entry": ent_b["id"],
            "version": 0}).get_json()
        ent_ds = A.BANK.add({
            "gid": "g1", "type": "ds", "name": "g1 ds",
            "session_label": "g1 label", "project": "TEST", "mouse": 1,
            "session": 2, "pipeline": "Incisor", "added_by": "tools-test",
            "events": [{"start": 9.5, "channel": 3}]})
        rd = cli.post("/api/curation/from-bank", json={
            "gid": "g1", "kind": "ds", "entry": ent_ds["id"],
            "version": 0}).get_json()
        A.PRESENCE.all = lambda: []
        k = cli.post("/api/curation/g1/%s/keep-only" % r2["kind"],
                     json={}).get_json()
        check("keep only this one hides the other Panning set",
              [h["kind"] for h in k.get("hidden") or []] == [rb["kind"]], k)
        check("and leaves the Checkup set alone",
              not (A.CURATE.get("g1", rd["kind"]) or {}).get("archived"))
        check("the one kept is in view",
              not A.CURATE.get("g1", r2["kind"]).get("archived"))

        # ---- keep only this one: versions ----
        vs = A.BANK.get(ent["id"])["versions"]
        v0 = min(vs, key=lambda v: v.get("v") or 0)
        ref = v0.get("id") or A.versionsmod.stable_id(ent["id"], v0)
        kv = cli.post("/api/bank/%s/version/%s" % (ent["id"], ref),
                      json={"action": "keep_only"}).get_json()
        vs = A.BANK.get(ent["id"])["versions"]
        check("a version's keep_only hides every other version",
              kv.get("ok") is True and all(bool(v.get("archived")) == (v.get("v") != 0)
                                   for v in vs),
              (kv, [(v.get("v"), v.get("archived")) for v in vs]))
        check("and the entry itself is not archived",
              not EB.entry_archived(A.BANK.get(ent["id"])))

        # ---- a note on a Lock/Braces/Eye row reaches the version ----
        bset = A.BRACES.create(ent_b["id"], "g1", None, {"measure": "csd"},
                               [{"i": 0, "was": 9.0, "now": 9.002,
                                 "peak": 1, "shift_ms": 2.0}], {})
        n = cli.post("/api/braces/set/%s/note" % bset["set_id"],
                     json={"row": 0, "note": "peak looks doubled"}).get_json()
        check("a row's note is kept on the alignment",
              (n.get("notes") or {}).get("0", {}).get("text")
              == "peak looks doubled", n)
        rep = A.BANK.align(ent_b["id"], {0: 9.002},
                           {"measure": "csd", "window_ms": 200,
                            "n_channels": 16},
                           dry_run=False, notes={0: n["notes"]["0"]},
                           by="tools-test")
        al = A.BANK.get(ent_b["id"])
        check("align writes the row's note onto the event",
              (al.get("events") or [{}])[0].get("note") == "peak looks doubled",
              (rep, al.get("events")))
        bad = cli.post("/api/braces/set/%s/note" % bset["set_id"],
                       json={"row": 5, "note": "x"})
        check("a note on a row that is not there is refused",
              bad.status_code == 400)

        # ---- the sync: notes on their own clock ----
        rec = A.CURATE.get("g1", r2["kind"])
        rows = A.CLOUD._curation_rows(rec)
        keys = {frozenset(r) for r in rows["curation_events"]}
        check("every event row carries the same keys (one batch)",
              len(keys) == 1 and {"note", "note_by", "note_at"} <= set(next(iter(keys))))
        target = rec["events"][1]
        theirs = [{"set_id": rows["curation_sets"][0]["id"],
                   "event_id": target["id"], "label": "garbage",
                   "decided_at": "2000-01-01T00:00:00+00:00",
                   "note": "their note", "note_by": "Rain",
                   "note_at": "2099-01-01T00:00:00+00:00"}]
        A.CLOUD._apply_curation(rows["curation_sets"], theirs)
        t2 = next(e for e in A.CURATE.get("g1", r2["kind"])["events"]
                  if e["id"] == target["id"])
        check("a newer note from elsewhere is taken",
              t2.get("note") == "their note" and t2.get("note_by") == "Rain", t2)
        check("and its old label is not", t2.get("label") == target.get("label"),
              (t2.get("label"), target.get("label")))

        # ---- Save: one set, read back ----
        fake = FakeCloud()
        A.CLOUD.cloud = fake
        s = cli.post("/api/curation/g1/%s/save" % r2["kind"], json={}).get_json()
        check("Save sends the set and the database confirms it",
              s.get("ok") and s.get("confirmed")
              and s.get("cloud_total") == s.get("total"), s)
        check("and only that set's rows went",
              {r["set_id"] for r in fake.rows.get("curation_events", [])}
              == {rows["curation_sets"][0]["id"]})
        shards.configure_safe(True, os.path.join(tmp, ".pisafe"))
        try:
            fake2 = FakeCloud()
            A.CLOUD.cloud = fake2
            s2 = cli.post("/api/curation/g1/%s/save" % r2["kind"],
                          json={}).get_json()
            check("in the practice layer Save looks done and sends nothing",
                  s2.get("confirmed") and not fake2.rows, (s2, fake2.rows))
        finally:
            shards.configure_safe(False)

        check("W is reserved for notes", "w" in C.RESERVED_KEYS)

        # ---- a merge pairs one detector's event with the other's ----
        evs = A.CURATE.get("g1", r2["kind"])["events"]
        inc = [e for e in evs if e.get("origin") == "incisor"]
        m = cli.post("/api/curation/g1/%s/merge" % r2["kind"],
                     json={"keep": inc[0]["id"], "drop": inc[1]["id"]})
        check("two of Incisor's are never merged",
              m.status_code == 400 and "Incisor" in (m.get_json() or {}).get(
                  "error", ""), m.get_json())
        rec = A.CURATE.get("g1", r2["kind"])
        for e in rec["events"]:
            if e["id"] == inc[1]["id"]:
                e["origin"] = "doppler"
        A.CURATE._write(rec)
        m2 = cli.post("/api/curation/g1/%s/merge" % r2["kind"],
                      json={"keep": inc[0]["id"], "drop": inc[1]["id"],
                            "stamp": "doppler"}).get_json()
        check("Incisor's with Doppler's merges, at Doppler's time",
              m2.get("ok") and abs((m2.get("event") or {}).get("start", 0)
                                   - inc[1]["start"]) < 1e-9, m2)
    finally:
        (A.BANK, A.CURATE, A.BRACES, A.STORE.record_activity,
         A.mirror_bank_soon, A._session_by_gid, A.CLOUD.cloud,
         A.CLOUD.curate) = saved
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("FAILED: %s" % ", ".join(FAILED) if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
