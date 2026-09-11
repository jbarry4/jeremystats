# -*- coding: utf-8 -*-
"""Import the reference channels from the Toothy workbook.

    python tools/import_toothy.py            # say what would change
    python tools/import_toothy.py --apply

Six sheets in that workbook, and they are not the same kind of thing. This
imports one of them, and the reasoning about the other five is the more
useful half of this file.

WHAT IS IMPORTED
    Toothy Input -- the ripple, fissure and hilus channels, plus the
    extraction note and whether the session still needs processing.

    These are anatomical landmarks: which channel sits at the fissure is a
    fact about where the probe ended up, and Jarvis had nowhere to put it, so
    the answer lived in a spreadsheet. All 62 rows match a recording Jarvis
    knows.

    And they are corroborated rather than trusted. The hilus channel the
    workbook names is labelled HIL in the layer sheet -- which came from a
    different spreadsheet, imported separately -- in 57 of 57 cases where
    both exist. Two independent sources agreeing is the best evidence either
    of them could have.

WHAT IS NOT, AND WHY
    Recording Sessions: DS#, Garbage#, Flag#, Deep Rev.
        Jarvis holds the decisions these count, one per candidate, with who
        made each and when. Of the 40 sessions where both exist, 22 agree
        exactly and 18 do not -- and m24 s4 reads spike 4 / garbage 734 in
        the workbook against spike 738 / garbage 0 here, which looks like
        two columns swapped in that row. Importing a count that disagrees
        with the decisions it is meant to summarise would give the lab two
        answers to "how many dentate spikes", one of which cannot be shown
        event by event. Use --reconcile to list the differences instead.

    Channel Data: side and location per channel
        Already imported, from the feeder sheet. 3,898 of 3,948 agree; the
        50 that do not are in four sessions (m13 s2, m11 s10, m33 s4,
        m33 s8) and are systematic rather than scattered -- for m11 s10 the
        workbook says CA1 for channels 8-17 where the sheet says CA1 SP.
        That is two spreadsheets disagreeing about a layer boundary, which
        is a question for whoever drew it and not something to resolve by
        picking the file that was read last. --reconcile lists these too.

    Manual Vs Auto
        A comparison of the automatic channel picks against the manual ones,
        with `Channels Match` reading No on all 52 rows. That is a result
        about the detector, not a fact about a recording, and putting it in
        the session record would file a conclusion where measurements go.

    Data Summary
        Per-mouse DS counts baseline against CNO, with percent change. Also
        a result, and one computed from the counts above -- so importing it
        would import the same disagreement one level further from the data.

    Sheet8
        Three numbers with no header. Nothing to import.
"""
import argparse
import collections
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl                                          # noqa: E402

WORKBOOK = "PTEN Toothy Data .xlsx"

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# The sheet's count column, and the label id Jarvis actually uses for it.
# `DS#` is the one that matters: the label is `spike`, and comparing against
# an id of "ds" reported Jarvis holding zero everywhere, which was a false
# conflict and very nearly a wrong conclusion.
COUNTS = [("DS#", "spike"), ("Garbage#", "garbage"),
          ("Flag#", "flag"), ("Deep Rev.", "review")]

LOCATION_TO_REGION = {
    "CA1": "ca1_sr", "CA1 SR": "ca1_sr", "CA1 SP": "ca1_sp",
    "CA1 SO": "ca1_so", "CA1 SLM": "ca1_slm", "DG OML1": "dg_oml1",
    "DG MML1": "dg_mml1", "DG GCL1": "dg_gcl1", "HIL": "hil",
    "DG GCL2": "dg_gcl2", "DG MML2": "dg_mml2", "DG OML2": "dg_oml2",
    "DG": "dg", "THAL": "thal", "DG2": "dg2",
}

SOURCE = "PTEN Toothy Data .xlsx"


def say(msg=""):
    OUT.write(msg + "\n")
    OUT.flush()


def clean(v):
    v = "" if v is None else str(v).strip()
    return "" if v.lower() in ("", "none", "nan", "n/a", "#n/a") else v


def num(v):
    try:
        return int(float(clean(v)))
    except (TypeError, ValueError):
        return None


def sess_key(v):
    m = re.match(r"^m(\d+)s(\d+)", clean(v).lower().replace(" ", ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def chan_of(v):
    """The digits out of "CSC12.ncs"."""
    m = re.search(r"(\d+)", clean(v))
    return int(m.group(1)) if m else None


def open_book():
    if not os.path.exists(WORKBOOK):
        say("Cannot find %s in %s" % (WORKBOOK, os.getcwd()))
        sys.exit(1)
    return openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True)


def read_sheet(wb, name):
    got = list(wb[name].iter_rows(values_only=True))
    if not got:
        return {}, []
    head = [clean(c) for c in got[0]]
    return ({h: i for i, h in enumerate(head) if h},
            [r for r in got[1:] if any(clean(c) for c in r)])


def barry_index(store):
    by = collections.defaultdict(list)
    for s in store.all_sessions():
        try:
            by[(int(s.get("mouse")), int(s.get("session")))].append(s)
        except (TypeError, ValueError):
            continue
    return by


def do_refs(store, index, wb, apply_it):
    """The ripple, fissure and hilus channels."""
    idx, body = read_sheet(wb, "Toothy Input")
    say("\n" + "=" * 70)
    say("REFERENCE CHANNELS  (ripple, fissure, hilus)")
    say("=" * 70)
    same = changed = added = skipped = 0
    for r in body:
        key = sess_key(r[idx.get("Session ID", 0)])
        if not key:
            continue
        recs = index.get(key) or []
        if len(recs) != 1:
            say("  m%-3d s%-3d  SKIPPED: Jarvis has %d recordings for this"
                % (key[0], key[1], len(recs)))
            skipped += 1
            continue
        rec = recs[0]

        want = {}
        for col, slot in (("Ripple Channel", "ripple_channel"),
                          ("Fissure Channel", "fissure_channel"),
                          ("Hilus Channel", "hilus_channel")):
            v = num(r[idx[col]]) if col in idx else None
            if v is not None:
                want[slot] = v
        note = clean(r[idx["Notes"]]) if "Notes" in idx else ""
        if note:
            want["extraction_note"] = note
        needs = clean(r[idx["Needs processing"]]) if "Needs processing" in idx else ""
        if needs:
            want["needs_processing"] = needs.lower().startswith("t")
        if not want:
            continue
        want["reference_channels_source"] = SOURCE

        diff = {k: v for k, v in want.items()
                if str(rec.get(k)) != str(v)}
        if not diff:
            same += 1
            continue
        if any(rec.get(k) is not None for k in diff if k != "reference_channels_source"):
            changed += 1
        else:
            added += 1
        say("  m%-3d s%-3d  %s"
            % (key[0], key[1],
               "  ".join("%s=%s" % (k.replace("_channel", ""), v)
                         for k, v in sorted(diff.items())
                         if k not in ("extraction_note",
                                      "reference_channels_source"))))
        if diff.get("extraction_note"):
            say("            %s" % diff["extraction_note"][:66])
        if apply_it:
            store.upsert_session(
                {"gid": rec.get("gid"), "key": rec.get("key"),
                 "loose_key": rec.get("loose_key"),
                 "mouse": key[0], "session": key[1],
                 "label": rec.get("label")},
                want)
    say("\n  newly set %d   changed %d   already agree %d   skipped %d"
        % (added, changed, same, skipped))


def do_reconcile(store, index, wb, curate, layers):
    """Where the workbook and Jarvis disagree. Reports; never writes."""
    say("\n" + "=" * 70)
    say("RECONCILIATION  (nothing is written by this)")
    say("=" * 70)

    idx, body = read_sheet(wb, "Recording Sessions")
    say("\nCuration counts, workbook against Jarvis's own decisions:")
    agree = differ = nocur = 0
    lines = []
    for r in body:
        key = sess_key(r[idx.get("Session ID", 0)])
        if not key or len(index.get(key) or []) != 1:
            continue
        gid = index[key][0].get("gid")
        rec = curate.get(gid, "ds") if gid else None
        if not rec:
            nocur += 1
            continue
        by = (curate.progress(rec).get("by_label") or {})
        bits, bad = [], False
        for col, lab in COUNTS:
            want = num(r[idx[col]]) if col in idx else None
            if want is None:
                continue
            got = by.get(lab) or 0
            bits.append("%s %s/%s" % (lab, want, got))
            if want != got:
                bad = True
        if not bits:
            continue
        if bad:
            differ += 1
            lines.append("  m%-3d s%-3d  %s" % (key[0], key[1], "  ".join(bits)))
        else:
            agree += 1
    say("  %d agree on every count, %d differ, %d have no curation set"
        % (agree, differ, nocur))
    say("  (workbook/Jarvis)")
    for line in lines:
        say(line)

    idx, body = read_sheet(wb, "Channel Data")
    say("\nChannel locations, workbook against the imported layer sheets:")
    same, bad = 0, []
    for r in body:
        key = sess_key(r[idx.get("sess", 0)])
        if not key or len(index.get(key) or []) != 1:
            continue
        ch = chan_of(r[idx["file"]]) if "file" in idx else None
        if ch is None and "eegnum" in idx:
            ch = num(r[idx["eegnum"]])
        loc = clean(r[idx["location"]]) if "location" in idx else ""
        want = LOCATION_TO_REGION.get(loc.upper()) if loc else None
        if ch is None or want is None:
            continue
        sheet = layers.get(index[key][0].get("gid"))
        if not sheet:
            continue
        got = (sheet.get("labels") or {}).get(str(ch))
        if got == want:
            same += 1
        else:
            bad.append((key, ch, loc, want, got))
    say("  %d agree, %d differ" % (same, len(bad)))
    per = collections.Counter((k[0], k[1]) for k, _c, _l, _w, _g in bad)
    for (m, s2), n in per.most_common():
        say("    m%-3d s%-3d  %d channel(s)" % (m, s2, n))
    for key, ch, loc, want, got in bad:
        say("      m%ds%d ch%-3d workbook %-9s (%s)   sheet %s"
            % (key[0], key[1], ch, loc, want, got or "unlabelled"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually write. Without it, only reports.")
    ap.add_argument("--reconcile", action="store_true",
                    help="list where the workbook and Jarvis disagree, and "
                         "write nothing at all")
    args = ap.parse_args()

    import backend.app as A

    wb = open_book()
    index = barry_index(A.STORE)
    say("Reading %s" % WORKBOOK)
    say("  sheets: %s" % ", ".join(wb.sheetnames))
    say("  Jarvis (mouse, session) keys: %d" % len(index))

    if args.reconcile:
        do_reconcile(A.STORE, index, wb, A.CURATE, A.LAYERS)
        say("\nNothing was written.")
        wb.close()
        return

    if not args.apply:
        say("\n*** DRY RUN -- nothing will be written. Add --apply to do it.")
    do_refs(A.STORE, index, wb, args.apply)
    say("\n" + ("Applied." if args.apply
                else "Nothing was written. Re-run with --apply."))
    wb.close()


if __name__ == "__main__":
    main()
