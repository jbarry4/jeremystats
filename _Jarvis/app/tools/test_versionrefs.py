# -*- coding: utf-8 -*-
"""Versions are found by ref, never by a number two versions share. Offline.

    python tools/test_versionrefs.py

`EventBank._version_ref` is what editing, archiving and deleting a version,
starting a curation set from one (`/api/curation/from-bank`) and putting one
back (`/restore`) all resolve through: an id, a derived id, or a number only
where it names one version -- a pre-id twin of a version is the same pass,
not a second version. Here on a throwaway bank holding two different
versions both numbered 3 and a pre-id copy of v2. Nothing real is touched.
"""
import copy
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import eventbank, versions as V  # noqa: E402

FAILED = []


def ok(what, cond, note=""):
    print("  %-66s %s" % (what, "ok" if cond else "FAILED"))
    if note and not cond:
        print("      " + str(note)[:300])
    if not cond:
        FAILED.append(what)


class Store:
    def provenance(self):
        return {"user": "zz", "machine": "zz-machine"}

    def __getattr__(self, name):
        return lambda *a, **k: None


def main():
    bank = eventbank.EventBank(tempfile.mkdtemp(prefix="zz-bank-"), Store())
    base = dict(type="ds", name="zz", project="zz", mouse=1, session=1,
                added_by="zz", curated=True, gid="zz-gid", pipeline="zz test")
    ev = lambda lab: [{"start": t, "label": lab} for t in (1, 2, 3)]
    eid = bank.add(dict(base, events=ev("spike")))["id"]
    for lab in ("garbage", "spike", "garbage"):
        time.sleep(0.01)
        bank.add(dict(base, id=eid, events=ev(lab)))
    rec = bank.get(eid)
    vs = rec["versions"]
    three = [x for x in vs if x["v"] == 3][0]
    # A second, different v3: another machine minted the same number.
    other = dict(copy.deepcopy(three), id="zz-other-3",
                 note="the other machine's v3", at="2099-01-01T00:00:00+00:00")
    # And a pre-id copy of v2: the same pass, recorded before ids.
    two = [x for x in vs if x["v"] == 2][0]
    twin = {k: val for k, val in copy.deepcopy(two).items()
            if k not in ("id", "changed", "gained", "lost", "moves")}
    rec["versions"] = vs + [other, twin]
    bank._save(rec)

    print("\nresolving")
    rec = bank.get(eid)
    ok("by id, exactly", bank._version_ref(rec, "zz-other-3") is not None
       and bank._version_ref(rec, "zz-other-3").get("note") == "the other machine's v3")
    try:
        bank._version_ref(rec, 3)
        ok("a number two versions share is refused", False, "it chose one")
    except eventbank.BankError as exc:
        ok("a number two versions share is refused, asking for the id",
           "Say which by its id" in str(exc), exc)
    ok("a number with only a pre-id copy beside it names one version",
       bank._version_ref(rec, "2").get("id") == two["id"])
    idless = [x for x in rec["versions"] if not x.get("id")][0]
    ok("a derived id finds the version written before ids",
       bank._version_ref(rec, V.stable_id(eid, idless)) is idless)

    print("\nediting and deleting")
    bank.edit_version(eid, "zz-other-3", {"note": "zz edited by id"})
    got = {x.get("id"): x.get("note") for x in bank.get(eid)["versions"]
           if x["v"] == 3}
    ok("editing by id changes that one only",
       got.get("zz-other-3") == "zz edited by id"
       and got.get(three["id"]) != "zz edited by id", got)
    bank.edit_version(eid, 2, {"note": "zz v2 by number"})
    ok("editing v2 keeps its pre-id copy in step (or it returns as a second)",
       all(x.get("note") == "zz v2 by number"
           for x in bank.get(eid)["versions"] if x.get("v") == 2))
    n = len(bank.get(eid)["versions"])
    bank.delete_version(eid, three["id"])
    after = bank.get(eid)["versions"]
    ok("deleting one v3 by id removes that one",
       not any(x.get("id") == three["id"] for x in after))
    ok("and leaves the other machine's v3",
       any(x.get("id") == "zz-other-3" for x in after))
    ok("exactly one version went", len(after) == n - 1, (n, len(after)))
    bank.delete_version(eid, two["id"])
    ok("deleting v2 takes its pre-id copy with it",
       not any(x.get("v") == 2 for x in bank.get(eid)["versions"]))
    try:
        bank.edit_version(eid, "no-such-id", {"note": "x"})
        ok("an unknown ref is refused", False)
    except eventbank.BankError:
        ok("an unknown ref is refused", True)

    print("\n" + ("ALL PASS" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
