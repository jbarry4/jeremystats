# -*- coding: utf-8 -*-
"""Merge duplicate identities across everything BARRY has recorded.

    python tools/merge_people.py                # say what would change
    python tools/merge_people.py --apply

The roster is compiled from the names stamped on the work, so a person who
changed how they typed their name -- or who had a machine credit their git
email for a while -- appears several times. Four entries here are two people:

    theexaminedexistence@gmail.com  ->  Shahriar Tafti
    Shahriar                       ->  Shahriar Tafti
    Rain Younger                   ->  Rain

That matters more than tidiness. `curation_events.decided_by` is a name, and
so is every bank entry's `added.by` and every layer version's `by`. Split
across three spellings, "who decided this" has three answers and none of them
is complete -- and 383 decisions were filed under an email address.

Every rename is recorded rather than silent. The old name goes into an
`aliases` list on the surviving roster entry, so the merge itself stays
readable afterwards: somebody reading a six-month-old figure caption can
still find out that the person credited as an email address is the person
credited by name now.

What is NOT touched: the activity log and the error log. They are
append-only records of what happened, and rewriting a name in them would be
editing history rather than reconciling a roster. The name in a log line is
what the machine believed at the time, which is itself a fact.
"""
import argparse
import collections
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# from -> to. Case-insensitive on the left.
MERGES = {
    "theexaminedexistence@gmail.com": "Shahriar Tafti",
    "shahriar": "Shahriar Tafti",
    "rain younger": "Rain",
}


def say(msg=""):
    OUT.write(msg + "\n")
    OUT.flush()


def target(name):
    """The surviving name for one that may be an alias."""
    return MERGES.get(str(name or "").strip().lower())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually write. Without it, only reports.")
    args = ap.parse_args()

    import backend.app as A

    counts = collections.Counter()
    if not args.apply:
        say("*** DRY RUN -- nothing will be written. Add --apply to do it.")
    say("\nMerging:")
    for a, b in sorted(MERGES.items()):
        say("  %-34s -> %s" % (a, b))

    # ---------------------------------------------------- curation decisions
    say("\n" + "=" * 70)
    say("CURATION DECISIONS  (decided_by, and the review trail)")
    say("=" * 70)
    for st in A.CURATE.all():
        gid, kind = st.get("gid"), st.get("kind")
        rec = A.CURATE.get(gid, kind)
        if not rec:
            continue
        touched = 0
        for ev in (rec.get("events") or []):
            want = target(ev.get("by"))
            if want:
                counts["decisions"] += 1
                touched += 1
                if args.apply:
                    ev["by"] = want
            for rv in (ev.get("reviews") or []):
                w2 = target(rv.get("by"))
                if w2:
                    counts["reviews"] += 1
                    if args.apply:
                        rv["by"] = w2
        # Whose set it is, and who put it on the bench.
        for field in ("assignee", "opened_by", "closed_by"):
            want = target(rec.get(field))
            if want:
                counts[field] += 1
                touched += 1
                if args.apply:
                    rec[field] = want
        if touched and args.apply:
            A.CURATE._write(rec)
        if touched:
            say("  %-16s %-4s  %d field(s)" % (gid, kind, touched))

    # ---------------------------------------------------- the event bank
    say("\n" + "=" * 70)
    say("EVENT BANK  (who added an entry, and who made each version)")
    say("=" * 70)
    # NOTE: `added.by` cannot be rewritten, and should not be.
    #
    # It is declared shards.FIRST -- whoever recorded it first stays
    # authoritative across the merge -- so a write to it lands in this
    # machine's shard and loses to the shard that recorded it. `update`
    # refuses it too. Both guards exist so that nobody editing a
    # description can quietly change who added the events, and both are
    # right.
    #
    # Seven entries stayed credited to the email because of it, and the
    # answer is not to force them: the roster folds aliases when it compiles
    # now, so the display and the counts are correct while every record
    # keeps what it actually said. Versions are still re-credited, being
    # ordinary mutable fields.
    #
    # Through `rename_person`, not `update`.
    #
    # `update` refuses to touch provenance -- deliberately, and rightly. The
    # first version of this tool patched `added` and `versions` through it
    # anyway and the guard silently dropped them: the dry run reported 125
    # changes and the apply made none, which is the worst way for a tool to
    # be wrong. Re-crediting a name is its own operation now, and it records
    # itself in the entry's history.
    for old_name in MERGES:
        want = MERGES[old_name]
        if args.apply:
            n = A.BANK.rename_person(old_name, want)
        else:
            n = 0
            for entry in A.BANK.all():
                if str((entry.get("added") or {}).get("by") or "").strip().lower() == old_name:
                    n += 1
                for v in (entry.get("versions") or []):
                    if str(v.get("by") or "").strip().lower() == old_name:
                        n += 1
        if n:
            counts["bank_fields"] += n
            say("  %-34s -> %-16s %d field(s)" % (old_name, want, n))

    # ---------------------------------------------------- layer sheets
    say("\n" + "=" * 70)
    say("LAYER SHEETS  (who made each version)")
    say("=" * 70)
    for sheet in A.LAYERS.all():
        gid = sheet.get("gid")
        live = A.LAYERS.get(gid)
        if not live:
            continue
        hit = 0
        for v in (live.get("versions") or []):
            want = target(v.get("by"))
            if want:
                hit += 1
                counts["layer_versions"] += 1
                if args.apply:
                    v["by"] = want
        if hit:
            say("  %-16s %d version(s)" % (gid, hit))
            if args.apply:
                A.LAYERS._write(live)

    # ---------------------------------------------------- the roster itself
    say("\n" + "=" * 70)
    say("THE ROSTER")
    say("=" * 70)
    for old, new in sorted(MERGES.items()):
        say("  drop %-34s keep %s" % (old, new))
        if args.apply:
            # The alias is kept on the survivor rather than thrown away: a
            # six-month-old caption crediting an email address should still
            # be traceable to the person who is credited by name now.
            keep = A.PEOPLE.details(new) or {}
            aliases = list(keep.get("aliases") or [])
            if old not in aliases:
                aliases.append(old)
            try:
                A.PEOPLE.add(new, None, None, aliases=aliases)
            except TypeError:
                # An older People that has no `aliases` field: the merge is
                # still worth doing, the record of it just lives here.
                pass
            A.PEOPLE.forget(old)
            counts["roster"] += 1

    say("\n" + "=" * 70)
    say("  " + "   ".join("%s=%d" % (k, v) for k, v in sorted(counts.items()))
        or "  nothing to change")
    say("\n" + ("Applied." if args.apply
                else "Nothing was written. Re-run with --apply."))
    say("\nNot touched, on purpose: the activity log and the error log. They "
        "are\nappend-only records of what happened, and the name in a log "
        "line is what\nthe machine believed at the time -- which is itself a "
        "fact.")


if __name__ == "__main__":
    main()
