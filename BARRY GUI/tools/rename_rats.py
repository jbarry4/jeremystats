"""rename_rats.py -- DEWEY's animals are rats, so their keys start `r`.

Every key in this lab has started `m` since there was a lab, because every
animal was a mouse. DEWEY's are rats. `ids.subject_prefix` now returns `r`
for that project, so anything read or written from here on uses it -- and
this brings the records that already exist across.

WHAT CHANGES

    key         m009_s002_2026-08-13_12-00-00 -> r009_s002_...
    loose_key   m009_s002                     -> r009_s002
    label       DEWEY m9 s2 Precon2 SPC ...   -> DEWEY r9 s2 ...
    shard file  m009_s002_...@machine.json    -> r009_s002_...@machine.json

and the same three fields on every banked entry that names one of these
recordings (`session_key`, `session_loose_key`, `session_label`).

WHAT DOES NOT

The gid. Everything that belongs to a recording -- bad channels, quality
flags, curation, layers, banked events -- hangs off the gid and not off the
key, which is the whole reason the gid exists. So nothing is detached by
this: the key is derived, it is allowed to change, and this is it changing.

Only DEWEY. Every other project's keys are untouched, and the check
`tools/check_ids_dewey.py` says so.

WHAT IT WILL NOT DO

Only this machine's shards, as ever. A shard belonging to another machine is
counted and named, with the machine that has to run this.

    python tools\\rename_rats.py           # say what would happen
    python tools\\rename_rats.py --apply   # do it
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import ids, sessreg, shards, store as storemod  # noqa: E402

LOGS = os.path.join(APP, "GUI_logs")
SESSIONS = os.path.join(LOGS, "sessions")


def pre_of(rec):
    """The prefix this record's project should be using."""
    return ids.subject_prefix(rec.get("project") or rec.get("group"))


#: `m9` as a whole token, so `m9` in a label changes and `2026` does not.
_LABEL_TOKEN = re.compile(r"(?<![A-Za-z0-9])m(\d+)(?![A-Za-z0-9])")


def wanted(rec):
    """What this record's key, loose key and label should be now -- or None.

    ONLY THE LETTER CHANGES.

    The obvious way to write this is to call `ids.make_key` with the new
    prefix and take what comes back. It is wrong, and the dry run said so:
    it wanted to re-key 361 records, PTEN and KCNT1 among them.

    The reason is that a key is built from the recording's START, and half
    of these records store a start that has since been converted to UTC --
    so recomputing gives `m002_s001_2022-03-18_19-22-43+00-00` where the
    stored key, written from a local folder name, says `..._15-22-43`.
    Both name the same recording. Recomputing would have renamed hundreds
    of shard files to say something subtly different, for no reason
    connected to rats at all.

    So this swaps the leading letter and touches nothing else. The
    timestamp half of the key stays byte-identical, which is the point: the
    key is not being recomputed, it is being re-lettered.
    """
    proj = rec.get("project") or rec.get("group")
    pre = ids.subject_prefix(proj)
    if pre == ids.DEFAULT_PREFIX:
        return None                      # a mouse is still a mouse
    key, loose = rec.get("key"), rec.get("loose_key")
    if not key or not key.startswith(ids.DEFAULT_PREFIX):
        return None                      # nothing to re-letter
    out = {"key": pre + key[1:]}
    if loose and loose.startswith(ids.DEFAULT_PREFIX):
        out["loose_key"] = pre + loose[1:]
    label = rec.get("label") or ""
    if label:
        out["label"] = _LABEL_TOKEN.sub(lambda m: pre + m.group(1), label)
    return out


def main():
    apply = "--apply" in sys.argv
    mine = shards.machine_id()
    STORE = storemod.Store(LOGS, auto_stage=False)
    REG = sessreg.Registry(STORE)

    print("this machine : %s\n" % mine)

    # ---- the session shards --------------------------------------------
    plan, foreign, clashes = [], [], []
    for f in sorted(glob.glob(os.path.join(SESSIONS, "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        want = wanted(rec)
        if not want or want["key"] == rec.get("key"):
            continue
        machine = (rec.get("_shard") or {}).get("machine")
        if machine != mine:
            foreign.append((f, machine))
            continue
        dest = os.path.join(SESSIONS, "%s@%s.json" % (want["key"], mine))
        if os.path.exists(dest):
            clashes.append((f, dest))
            continue
        plan.append((f, dest, rec, want))

    print("session records to re-key : %d" % len(plan))
    for f, dest, rec, want in plan[:6]:
        print("   %-40s -> %s" % (rec.get("key"), want["key"]))
        print("      %s" % want["label"])
    if len(plan) > 6:
        print("   ... and %d more" % (len(plan) - 6))
    if foreign:
        machines = sorted({m for _f, m in foreign})
        print("\nleft alone -- another machine's shard : %d" % len(foreign))
        print("   run this there too: %s" % ", ".join(str(m) for m in machines))
    if clashes:
        print("\nleft alone -- the new name is already taken : %d"
              % len(clashes))
        for f, dest in clashes[:5]:
            print("   %s" % os.path.basename(f))

    # ---- records a stale server put back ---------------------------------
    #
    # A Jarvis that was started before `ids.subject_prefix` existed still
    # computes `m` keys, so every recording it touches gets a record under
    # the old name -- with a new gid, because nothing matches the `r` record
    # that is now there. This is how the same recording ends up listed
    # twice. Running this again mops them up; restarting that Jarvis is what
    # stops them appearing.
    live = REG.all()
    by_path = {}
    for r in live:
        if r.get("retired"):
            continue
        for p in (r.get("paths") or []):
            by_path.setdefault(os.path.normcase(str(p)), []).append(r)

    stale = []
    for _p, claimants in by_path.items():
        if len(claimants) < 2:
            continue
        keyed = [r for r in claimants if (r.get("key") or "").startswith(pre_of(r))]
        old = [r for r in claimants
               if (r.get("key") or "").startswith(ids.DEFAULT_PREFIX)
               and ids.subject_prefix(r.get("project")) != ids.DEFAULT_PREFIX]
        if keyed and old:
            for r in old:
                if r not in stale:
                    stale.append(r)

    print("\nold-prefix records a stale server re-created : %d" % len(stale))
    for r in stale[:6]:
        print("   %-34s gid=%s" % (r.get("key"), r.get("gid")))
    if stale:
        print("   Restart Jarvis: one that predates this change keeps making "
              "them.")

    # ---- the banked entries --------------------------------------------
    by_gid = {}
    for _f, _d, rec, want in plan:
        if rec.get("gid"):
            by_gid[rec["gid"]] = want

    bank_plan = []
    from backend import eventbank as ebmod           # noqa: E402
    BANK = ebmod.EventBank(os.path.join(LOGS, "event_bank"), STORE)
    for e in BANK.summaries():
        want = by_gid.get(e.get("gid"))
        if not want:
            continue
        if (e.get("session_key") == want.get("key")
                and e.get("session_loose_key") == want.get("loose_key")
                and e.get("session_label") == want.get("label")):
            continue
        bank_plan.append((e, want))

    print("\nbanked entries to re-label : %d" % len(bank_plan))
    for e, want in bank_plan[:5]:
        print("   %-34s -> %s" % (e.get("session_label"), want["label"]))

    if not apply:
        print("\nDry run. Nothing was written. Re-run with --apply to act.")
        return 0
    if not plan and not bank_plan and not stale:
        print("\nNothing to do.")
        return 0

    print("\napplying...")
    done = 0
    for f, dest, rec, want in plan:
        rec.update(want)
        # `_at` is the merge's per-field clock; the three fields just
        # changed, so they are stamped, or another machine's older copy
        # would win the next time the two are merged.
        at = rec.setdefault("_at", {})
        stamp = STORE.provenance().get("at")
        for k in want:
            at[k] = stamp
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=2, sort_keys=True, ensure_ascii=False)
        os.remove(f)
        done += 1
        if done % 50 == 0:
            print("  ... %d of %d" % (done, len(plan)))

    # Retired, not deleted: a record a stale server made is still a record
    # somebody could want to look at, and `tree` leaves retired rows out.
    for r in stale:
        REG._patch(r, {"retired": True})
    if stale:
        print("  retired %d record(s) written under the old prefix" % len(stale))

    for e, want in bank_plan:
        try:
            BANK.update(e["id"], {k2: v for k2, v in (
                ("session_key", want.get("key")),
                ("session_loose_key", want.get("loose_key")),
                ("session_label", want.get("label"))) if v})
        except Exception as exc:                             # noqa: BLE001
            print("  ! could not relabel %s: %s" % (e.get("id"), exc))

    print("\nDone. %d record(s) re-keyed, %d banked entry(s) relabelled."
          % (done, len(bank_plan)))
    print("The Data Bank mirror rewrites itself on the next sync, under "
          "DEWEY/r<n>/ instead of DEWEY/m<n>/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
