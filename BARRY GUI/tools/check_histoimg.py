# -*- coding: utf-8 -*-
"""Do the histology slide filenames still read the way Jarvis thinks?

WHY THIS EXISTS
---------------
`backend/histoimg.py` treats the filenames on `E:\\Joebot Multisite 2026` as a
second source of truth. They carry what the spreadsheet does not -- whether a
track missed, whether a region is a guess -- and they were typed by hand over
months, so hippocampus is spelled four ways and the side token turns up on
either end of the region.

A parser over names like that fails quietly. It reads eight of the nine
tokens, drops the ninth, and the listing looks fine. So this asserts the
whole batch, by name:

  1. every one of the 63 files parses to a rat and at least one region
  2. nothing lands in `unparsed` -- every token in this batch is accounted
     for by the tables, so anything there is a spelling nobody has taught it
  3. the genuinely ambiguous names are reported ambiguous, NOT resolved --
     `J11_R_Dhc_L_Maybe` carries a side on both ends and picking one would
     label a hemisphere somebody is going to analyse
  4. the four spellings of hippocampus land on one id, and the side token is
     read the same whether it comes before or after the region
  5. the derived cache, wherever it exists, still matches its source's
     `size:mtime` -- a stale JPEG of a re-photographed slide is worse than
     no JPEG

THE 63 NAMES ARE A FIXTURE, NOT A DIRECTORY WALK
------------------------------------------------
So this runs on a machine that has never had the drive, which is most of
them, and so that a file quietly vanishing from `E:` is a failure here rather
than a smaller test that still passes. When the drive IS present the listing
is compared against the fixture, both ways.

Run from PowerShell (sec 9 -- under bash the harness tooling on this machine
writes nothing and a whole suite reads as clean):

    python tools\\check_histoimg.py
    python tools\\check_histoimg.py --time "E:\\Joebot Multisite 2026\\J3\\J3_ACC.tif"
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import histoimg                              # noqa: E402

FAIL = []
CHECKS = [0]


def ok(what, cond, detail=""):
    CHECKS[0] += 1
    print(("  ok   " if cond else "  FAIL ") + what
          + (("   " + detail) if detail and not cond else ""))
    if not cond:
        FAIL.append(what)


# The batch as it stands, rat by rat. Spaces, inconsistent case and the one
# slide that is both .jpg and .tif are all deliberate.
BATCH = {
    "J3": ["J3_ACC.tif", "J3_DHc.tif", "J3_OFC_L_Full.tif", "J3_OFC_R.tif",
           "J3_OFC_R_Full.tif", "J3_PRH_R.tif"],
    "J4": ["J4_ACC.tif", "J4_DHc_L.tif", "J4_DHc_R.tif",
           "J4_Missed_Por_L.tif", "J4_Missed_Por_R.tif",
           "J4_Missed_Prh_L.tif", "J4_Missed_Prh_R.tif",
           "J4_OFC_Maybe_insular.tif", "J4_RSC_L.tif", "J4_RSC_R.tif"],
    "J5": ["J5_OFC_L.tif", "J5_OFC_R_ACC_.tif", "J5_RSC_L_maybe_V2.tif",
           "J5_RSC_R.tif", "J5_hpc_L.tif", "J5_hpc_R.tif", "J5_not por.tif"],
    "J6": ["J6_HPC_L.tif", "J6_HPC_R_Maybe.tif", "J6_Not POR.tif",
           "J6_Not POR_R.tif", "J6_OFC_ACC.tif", "J6_Prh_L.tif",
           "J6_Prh_R_Maybe.tif", "J6_rsc.tif"],
    "J7": ["J7_HPC.tif", "J7_OFC_ACC.tif", "J7_PRH_L_Maybe.tif",
           "J7_RSC_PRH_R.tif", "J7_not_POR.tif"],
    "J8": ["J8_ACC.tif", "J8_HPC_L_Maybe.tif", "J8_HPC_R_Maybe.tif",
           "J8_Maybe_L_PRH.tif", "J8_No_POR.tif", "J8_OFC.tif",
           "J8_RSC_Maybe.tif"],
    "J9": ["J9_DHC_Not.tif", "J9_Maybe_Prh_R.tif", "J9_OFC_ACC.tif",
           "J9_RSC_Maybe.tif"],
    "J10": ["J10_ACC_L.tif", "J10_ACC_R.tif", "J10_HPC_L_Maybe.tif",
            "J10_HPC_R_JustMissed.tif", "J10_Not_POR.tif",
            "J10_OFC_Maybe.tif", "J10_PRH_R_Maybe.tif",
            "J10_RSC_L_Maybe.tif", "J10_RSC_R.tif"],
    "J11": ["J11_L_OFC_ACC.jpg", "J11_L_OFC_ACC.tif", "J11_L_Prh.tif",
            "J11_RSC.tif", "J11_R_ACC.tif", "J11_R_Dhc_L_Maybe.tif",
            "J11_R_Prh.tif"],
}

ALL = [(rat, name) for rat in BATCH for name in BATCH[rat]]

# The names that cannot be resolved, and why. Anything here that comes back
# with a side is the failure this file was written for.
AMBIGUOUS = {
    "J11_R_Dhc_L_Maybe.tif":
        "R before the region and L after it; nothing in the name decides",
}

# Names whose full reading is asserted, because they are the ones that
# distinguish a table-driven parser from a lucky regex.
EXPECT = [
    # two regions on one slide
    ("J6_OFC_ACC.tif", {"rat": "J6", "region_ids": ["ofc", "acc"],
                        "side": None, "side_specific": False}),
    ("J7_RSC_PRH_R.tif", {"rat": "J7", "region_ids": ["rsc", "prh"],
                          "side": "right", "side_where": "after"}),
    ("J11_L_OFC_ACC.tif", {"rat": "J11", "region_ids": ["ofc", "acc"],
                           "side": "left", "side_where": "before"}),
    # a side token sitting BETWEEN two regions: which region it belongs to
    # is unclear, but the slide is a right-hand slide either way
    ("J5_OFC_R_ACC_.tif", {"rat": "J5", "region_ids": ["ofc", "acc"],
                           "side": "right", "side_where": "inside",
                           "side_ambiguous": False}),
    # hippocampus, four spellings, one id
    ("J3_DHc.tif", {"region_ids": ["hpc"], "side_specific": False}),
    ("J9_DHC_Not.tif", {"region_ids": ["hpc"], "verdict_ids": ["not"]}),
    ("J5_hpc_L.tif", {"region_ids": ["hpc"], "side": "left"}),
    ("J6_HPC_L.tif", {"region_ids": ["hpc"], "side": "left"}),
    # side before the region
    ("J8_Maybe_L_PRH.tif", {"region_ids": ["prh"], "side": "left",
                            "side_where": "before",
                            "verdict_ids": ["maybe"]}),
    ("J11_L_Prh.tif", {"region_ids": ["prh"], "side": "left"}),
    # and after it
    ("J4_DHc_L.tif", {"region_ids": ["hpc"], "side": "left",
                      "side_where": "after"}),
    ("J10_ACC_R.tif", {"region_ids": ["acc"], "side": "right",
                       "side_where": "after"}),
    # verdicts, folded onto three words, raw kept
    ("J10_HPC_R_JustMissed.tif", {"verdict_ids": ["missed"],
                                  "side": "right"}),
    ("J4_Missed_Por_L.tif", {"verdict_ids": ["missed"], "region_ids": ["por"],
                             "side": "left"}),
    ("J8_No_POR.tif", {"verdict_ids": ["not"], "region_ids": ["por"],
                       "side_specific": False}),
    ("J7_not_POR.tif", {"verdict_ids": ["not"], "region_ids": ["por"]}),
    # a space instead of an underscore, twice
    ("J5_not por.tif", {"rat": "J5", "verdict_ids": ["not"],
                        "region_ids": ["por"], "side_specific": False}),
    ("J6_Not POR_R.tif", {"rat": "J6", "verdict_ids": ["not"],
                          "region_ids": ["por"], "side": "right"}),
    # notes, verbatim and uninterpreted
    ("J3_OFC_L_Full.tif", {"notes": ["Full"], "side": "left"}),
    ("J4_OFC_Maybe_insular.tif", {"notes": ["insular"],
                                  "verdict_ids": ["maybe"]}),
    ("J5_RSC_L_maybe_V2.tif", {"notes": ["V2"], "verdict_ids": ["maybe"],
                               "side": "left"}),
    # lower case throughout
    ("J6_rsc.tif", {"region_ids": ["rsc"], "side_specific": False}),
]


def check_parses():
    print("\nEvery name parses to a rat and a region")
    bad_rat = [n for _r, n in ALL if histoimg.parse_name(n)["rat"] is None]
    ok("all 63 carry a rat", not bad_rat, "no rat: %s" % bad_rat)
    bad_reg = [n for _r, n in ALL if not histoimg.parse_name(n)["regions"]]
    ok("all 63 carry at least one region", not bad_reg,
       "no region: %s" % bad_reg)
    wrong_rat = [(n, histoimg.parse_name(n)["rat"]) for r, n in ALL
                 if histoimg.parse_name(n)["rat"] != r]
    ok("the rat in the name is the folder it is in", not wrong_rat,
       str(wrong_rat))
    ok("the fixture is 63 files", len(ALL) == 63, "got %d" % len(ALL))


def check_unparsed():
    print("\nNothing is read half-way")
    left = [(n, histoimg.parse_name(n)["unparsed"]) for _r, n in ALL
            if histoimg.parse_name(n)["unparsed"]]
    ok("no token in this batch lands in `unparsed`", not left, str(left))
    # The other half of the claim: unparsed is not empty because it is dead.
    made_up = histoimg.parse_name("J12_Thalamus_Probably_weird.tif")
    ok("an unknown token DOES land in `unparsed`",
       set(made_up["unparsed"]) == {"Thalamus", "Probably", "weird"},
       str(made_up["unparsed"]))
    ok("...and an unknown name is not given a region it does not have",
       made_up["regions"] == [], str(made_up["regions"]))


def check_ambiguous():
    print("\nThe ambiguous names are reported, not resolved")
    for name, why in AMBIGUOUS.items():
        p = histoimg.parse_name(name)
        ok("%s is ambiguous (%s)" % (name, why), p["side_ambiguous"] is True)
        ok("%s does not claim a side" % name, p["side"] is None,
           "claimed %r" % p["side"])
        ok("%s still says which two it is between" % name,
           p["side_candidates"] == ["left", "right"],
           str(p["side_candidates"]))
        ok("%s reads as ambiguous to a person" % name,
           "side unclear" in histoimg.describe(p), histoimg.describe(p))
    others = [n for _r, n in ALL
              if n not in AMBIGUOUS and histoimg.parse_name(n)["side_ambiguous"]]
    ok("nothing else in the batch is ambiguous", not others, str(others))


def check_expectations():
    print("\nThe readings that distinguish a table from a lucky regex")
    for name, want in EXPECT:
        got = histoimg.parse_name(name)
        bad = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
        ok("%-28s %s" % (name, histoimg.describe(got)), not bad, str(bad))


def check_spellings():
    print("\nThe vocabulary is data, and it covers what is there")
    spellings = {}
    for _r, n in ALL:
        for reg in histoimg.parse_name(n)["regions"]:
            spellings.setdefault(reg["id"], set()).add(reg["raw"])
    hpc = spellings.get("hpc") or set()
    ok("hippocampus is spelled %d ways and lands on one id" % len(hpc),
       hpc == {"DHc", "DHC", "HPC", "hpc", "Dhc"}, str(sorted(hpc)))
    ok("every region id has a printable name",
       all(i in histoimg.REGION_NAMES for i in spellings), str(spellings))
    ok("the verdict vocabulary is three words",
       set(histoimg.VERDICTS.values()) == {"missed", "not", "maybe"},
       str(sorted(set(histoimg.VERDICTS.values()))))
    # The raw word survives the fold, which is the point of keeping it.
    j10 = histoimg.parse_name("J10_HPC_R_JustMissed.tif")
    ok("`JustMissed` folds to `missed` and keeps its own word",
       j10["verdicts"] == [{"id": "missed", "raw": "JustMissed"}],
       str(j10["verdicts"]))


def check_cache():
    """The derived copies, where any exist, still describe their source."""
    print("\nThe derived cache matches what it was derived from")
    try:
        histoimg.cache_dir()
    except RuntimeError:
        histoimg.configure(os.path.join(APP, "GUI_logs"))
    have_drive = histoimg.have_drive()
    if not have_drive:
        print("    (%s is not on this machine -- the cache is checked "
              "against what is cached, not against the drive)"
              % histoimg.root())

    checked, stale, orphan = 0, [], []
    for rat, name in ALL:
        paths = histoimg._cache_paths(rat, name)
        if not (os.path.isfile(paths["web"])
                or os.path.isfile(paths["thumb"])
                or os.path.isfile(paths["sidecar"])):
            continue
        checked += 1
        side = histoimg._read_sidecar(paths)
        if not (os.path.isfile(paths["web"])
                and os.path.isfile(paths["thumb"]) and side.get("sig")):
            orphan.append(name)
            continue
        if have_drive:
            src = os.path.join(histoimg.root(), rat, name)
            sig = histoimg._sig(src)
            if sig and side.get("sig") != sig:
                stale.append((name, side.get("sig"), sig))
    if not checked:
        print("    (nothing derived yet -- run the derive route or "
              "histoimg.derive_all())")
    ok("no derived pair is half-written (%d checked)" % checked, not orphan,
       str(orphan))
    ok("no derived copy is stale against its source", not stale, str(stale))
    if have_drive:
        idx = histoimg.index()
        on_disk = {(r["rat"], row["file"])
                   for r in idx["rats"] for row in r["files"]}
        ok("the drive holds exactly the 63 names in this fixture",
           on_disk == set(ALL),
           "only on disk: %s | only in fixture: %s"
           % (sorted(on_disk - set(ALL)), sorted(set(ALL) - on_disk)))
        ok("the listing agrees nothing is unparsed", not idx["unparsed"],
           str(idx["unparsed"]))
        ok("the listing reports the same one ambiguous name",
           set(idx["ambiguous"]) == set(AMBIGUOUS), str(idx["ambiguous"]))


def time_one(path):
    """Re-measure the number in histoimg.py's docstring, on a real file."""
    import time as _t
    histoimg.configure(os.path.join(APP, "GUI_logs"))
    rat = os.path.basename(os.path.dirname(path))
    name = os.path.basename(path)
    mb = os.path.getsize(path) / 1e6
    t0 = _t.time()
    res = histoimg.derive_one(rat, name, force=True)
    dt = _t.time() - t0
    if not res.get("ok"):
        print("failed: %s" % res.get("error"))
        return 1
    print("%s  %.1f MB  %s px" % (name, mb, res["pixels"]))
    print("  %.2fs end to end  -> %.0f MB/s of source"
          % (dt, mb / dt if dt else 0))
    print("  web   %s px  %.0f kB" % (res["web_px"], res["web_bytes"] / 1e3))
    print("  thumb %s px  %.0f kB" % (res["thumb_px"],
                                      res["thumb_bytes"] / 1e3))
    print("  histoimg.MB_PER_SECOND is %.0f" % histoimg.MB_PER_SECOND)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--time", metavar="FILE",
                    help="re-measure the derive cost on one real slide")
    args = ap.parse_args()
    if args.time:
        return time_one(args.time)

    print("Histology slide names and derived copies")
    print("  root: %s%s" % (histoimg.root(),
                            "" if histoimg.have_drive()
                            else "   (not on this machine)"))
    check_parses()
    check_unparsed()
    check_ambiguous()
    check_expectations()
    check_spellings()
    check_cache()
    print("\n%d checks, %d failed" % (CHECKS[0], len(FAIL)))
    for f in FAIL:
        print("  - " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
