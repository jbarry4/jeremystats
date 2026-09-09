# -*- coding: utf-8 -*-
"""Pull mouse details from the lab's colony Google Sheet.

The sheet is the colony log: who is alive, what genotype, what was implanted
and when. BARRY has slots for all of that already -- the mouse book has
`genotype`, `sex`, `dob`, `implant`, `status` and has simply never had
anything to put in them, so every one of those questions has been answered by
opening the spreadsheet.

Mouse facts only, deliberately. The sheet also carries session numbers and
per-procedure leads, and recordings are the one thing BARRY should learn from
the recordings themselves: a session that exists because a spreadsheet says
so is a session nobody can open.

    python tools/import_colony.py                 # say what would change
    python tools/import_colony.py --apply
    python tools/import_colony.py --apply --all   # unknown mice too

Read-only against Google, and one direction only. BARRY writing back into a
sheet people edit by hand would invite exactly the conflict class the shard
files spent a fortnight untangling, and a sheet has no per-field timestamps
to resolve it with.

Only mice BARRY already recognises are touched, unless --all. The sheet holds
241 mice and BARRY knows nineteen of them; importing the rest would fill the
mouse book with animals nobody here has recorded.
"""
import argparse
import collections
import csv
import io
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# The published CSV. "Publish to web" rather than the API: no key to store,
# no library to add, and nothing that stops working when a token expires.
SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vTIYQlXuxUx5YexusKnFoY"
    "5_UQgw4OfLFkyvz6gh8VUEcnYhjtOsZMP2btL9TO0dGsioAJ2WzH4qUTb/pub?output=csv"
)

# Where a local copy is kept, so a re-run with no network still works and so
# the last thing imported can be looked at afterwards.
CACHE = os.path.join("GUI_logs", ".cache", "colony.csv")

# The probe columns, and what each says about where it went.
#
# Worth importing as a prompt, not as evidence. I first wrote that this was
# an independent check on the hemisphere a recording claims; it is not. The
# sheet records what was planned, its dates are loose, and every session is
# checked by hand afterwards -- so a disagreement between this and a
# recording means go and look, not that the recording is wrong.
PROBES = [
    ("H3 probe (L)", "H3 (L)"),
    ("H3 probe (R)", "H3 (R)"),
    ("H10 probe (L)", "H10 (L)"),
    ("H10 probe (R)", "H10 (R)"),
    ("H10 opto (L)", "H10 opto (L)"),
    ("H10 opto (R)", "H10 opto (R)"),
]

# The three loci the sheet genotypes separately.
LOCI = ["YH", "SST", "PV"]

# Attached to every record this writes.
#
# The colony sheet is a working log, not a register: the dates are
# approximate and each session is checked by hand afterwards. Whoever reads
# "H3 (L) 2/24/2026" six months from now needs to know that before they use
# it, and the only place they are certain to be looking is the record itself.
IMPORT_NOTE = (
    "From the colony Google Sheet. Dates are approximate and the implant "
    "column records what was planned rather than what a given recording "
    "turned out to be — sessions are checked by hand. Treat as a "
    "prompt to go and look, not as the answer."
)


def say(msg=""):
    OUT.write(msg + "\n")
    OUT.flush()


def clean(v):
    v = "" if v is None else str(v).strip()
    return "" if v.upper() in ("", "N/A", "?", "NA") else v


def fetch(url, use_cache=False):
    """The sheet, as rows. Cached, so a re-run without network still works."""
    if use_cache and os.path.exists(CACHE):
        say("  using the cached copy at %s" % CACHE)
        return io.open(CACHE, encoding="utf-8-sig").read()
    req = urllib.request.Request(url, headers={"User-Agent": "BARRY-GUI"})
    text = urllib.request.urlopen(req, timeout=90).read().decode("utf-8-sig")
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        io.open(CACHE, "w", encoding="utf-8").write(text)
    except OSError:
        pass
    return text


def attrs_for(row):
    """The mouse-level facts in one row, as BARRY's attributes.

    Anything not in the sheet is left out rather than written empty: an
    attribute that is absent means "the sheet does not say", and one written
    as "" means "the sheet says nothing", which are different and only one of
    them is true.
    """
    out = {}

    cage = clean(row.get("Cage ID"))
    if cage:
        # RETIRED is a cage that no longer exists rather than a cage id, and
        # recording it as one would put a hundred mice in the same box.
        out["cage"] = cage if cage.upper() != "RETIRED" else "retired"

    sex = clean(row.get("Sex"))
    if sex:
        out["sex"] = sex.upper().rstrip("?") if sex.upper().rstrip("?") in ("M", "F") else sex

    # Three loci, one line. Kept as written -- "het" and "Het" and "hom" are
    # the lab's spellings and normalising them here would quietly disagree
    # with the sheet somebody is reading next to this.
    geno = []
    for locus in LOCI:
        v = clean(row.get(locus))
        if v:
            geno.append("%s %s" % (locus, v.lower()))
    if geno:
        out["genotype"] = ", ".join(geno)

    dob = clean(row.get("DOB"))
    if dob:
        out["dob"] = dob

    role = clean(row.get("Role"))
    if role:
        out["role"] = role

    # Alive, and what ended it. One field, because "No" on its own invites
    # the question this can answer in the same breath.
    alive = clean(row.get("Alive"))
    perfused = clean(row.get("Perfuse"))
    if alive:
        if alive.lower().startswith("y"):
            out["status"] = "alive"
        else:
            out["status"] = ("perfused %s" % perfused) if perfused else "dead"
    elif perfused:
        out["status"] = "perfused %s" % perfused

    # What went in, and where.
    #
    # Take it as a record of intent rather than of fact. The lab checks each
    # session by hand, and the sheet's own dates are approximate -- so this
    # says what was planned and roughly when, not what a given recording
    # actually is. It is a prompt to go and look, never an answer, and
    # specifically NOT a check on the hemisphere a recording claims.
    #
    # A value that is not a date -- "MISS", "x", "yes" -- is kept verbatim:
    # it is what the surgeon wrote, and turning "MISS" into a date would be
    # inventing one.
    got = []
    plate = clean(row.get("Headplate"))
    if plate:
        got.append("headplate %s" % plate)
    for col, label in PROBES:
        v = clean(row.get(col))
        if v:
            got.append("%s %s" % (label, v))
    if got:
        out["implant"] = " · ".join(got)

    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually write. Without it, only reports.")
    ap.add_argument("--all", action="store_true",
                    help="include mice BARRY has never recorded")
    ap.add_argument("--offline", action="store_true",
                    help="use the cached copy instead of fetching")
    ap.add_argument("--url", default=SHEET_URL)
    args = ap.parse_args()

    import backend.app as A

    say("Fetching the colony sheet...")
    text = fetch(args.url, use_cache=args.offline)
    rows = list(csv.DictReader(io.StringIO(text)))
    say("  %d rows, %d columns" % (len(rows), len(rows[0]) if rows else 0))

    # Which mice BARRY has recordings for, and in which project. The project
    # is not in the sheet -- it comes from where the recordings live, which
    # is the only place that knows.
    project_of = {}
    for s in A.STORE.all_sessions():
        try:
            m = int(s.get("mouse"))
        except (TypeError, ValueError):
            continue
        proj = s.get("project")
        if proj:
            project_of.setdefault(m, proj)
    say("  BARRY has recordings for %d mice" % len(project_of))

    by_mouse = {}
    for r in rows:
        mid = clean(r.get("Mouse ID"))
        if not mid.isdigit():
            continue
        by_mouse[int(mid)] = r
    say("  the sheet lists %d mice" % len(by_mouse))

    known = sorted(set(by_mouse) & set(project_of))
    unknown = sorted(set(by_mouse) - set(project_of))
    say("  %d of them BARRY has recordings for; %d it does not"
        % (len(known), len(unknown)))
    if not args.apply:
        say("\n*** DRY RUN -- nothing will be written. Add --apply to do it.")

    targets = known + (unknown if args.all else [])
    changed = same = noted = 0
    fields = collections.Counter()

    say("\n" + "=" * 70)
    for m in targets:
        proj = project_of.get(m) or "KCNT1"
        want = attrs_for(by_mouse[m])
        if not want:
            continue
        have = ((A.MICE.get(proj, m) or {}).get("attrs")) or {}
        # Only what differs. Writing the same values back restamps the
        # record, and a restamped record is pushed to the cloud as though it
        # were an edit -- the loop the roster and the layer sheets were both
        # stuck in.
        diff = {k: v for k, v in want.items()
                if str(have.get(k) or "").strip() != str(v).strip()}
        if not diff:
            same += 1
            # The attributes agree, but the caveat may not be on the record
            # yet -- it is the thing somebody reads at the moment they are
            # looking at one of these dates, so it is worth a write of its
            # own when it is missing.
            if args.apply and (A.MICE.get(proj, m) or {}).get("note") != IMPORT_NOTE:
                A.MICE.set(proj, m, {}, note=IMPORT_NOTE)
                noted += 1
            continue
        changed += 1
        say("  %s m%-5s" % (proj, m))
        for k in sorted(diff):
            fields[k] += 1
            was = have.get(k)
            say("      %-9s %s%s"
                % (k, ("%s -> " % was) if was else "", diff[k][:64]))
        if args.apply:
            # The note travels with the record and is what the housekeeping
            # view shows, so the caveat is attached to the data rather than
            # living only in a changelog nobody reads at the moment they are
            # looking at a date.
            A.MICE.set(proj, m, diff, note=IMPORT_NOTE)

    say("\n" + "=" * 70)
    say("  %d mice would change, %d already agree" % (changed, same))
    if noted:
        say("  %d had the source note added" % noted)
    if fields:
        say("  fields: %s" % dict(fields))
    if unknown and not args.all:
        say("  %d mice in the sheet have no recordings here and were skipped."
            % len(unknown))
        say("  Pass --all to bring them in as well.")
    say("\n" + ("Applied." if args.apply
                else "Nothing was written. Re-run with --apply."))


if __name__ == "__main__":
    main()
