# -*- coding: utf-8 -*-
"""clipping_loss.py -- how much of the DEWEY cue-pair data is REALLY gone.

THE QUESTION
------------
Spark measures amplifier saturation per cue pair, per window, per channel,
and banks it. Add those up and the headline is thousands of lost "blocks",
which is frightening and is also the wrong unit to be frightened by.

A block is one event, in one window, on ONE WIRE. A brain region is not one
wire. Left PER is CSC 5, 6, 7 and 8, so losing CSC 5 does not lose Left PER
-- the analysis simply measures it on CSC 6 instead (`coupling.
representative`: the lowest-numbered wire that is neither bad nor clipped).
A region is lost only when EVERY wire it has is unusable, and a matrix cell
is lost only when one of its two regions is.

So this walks the same ladder the summary has to walk:

    channel-blocks   what the bank's headline counts
    region-blocks    after redundancy: a region survives on any one wire
    pair-blocks      what actually costs a cell of the connectivity matrix
    histology        regions lost whatever the amplifier did, counted apart

EVERY NUMBER HERE CARRIES ITS UNIT, because the four are not comparable and
the whole point of the exercise is that the first one is the misleading one.

WHAT IT DOES NOT DO
-------------------
It does not re-implement the accounting. `backend/coupling.py` already owns
it -- `excluded_for`, `channel_sanity`, `blocked_pairs` -- and a second
implementation that agreed would prove nothing. The only thing computed
twice on purpose is the channel-block TOTAL: once straight off the raw JSON
here, once through `coupling.excluded_for`, and the two are asserted equal
(`--check`).

ABSENT IS NOT ZERO
------------------
An entry banked before anybody ran the clipping check has empty lists that
mean "nobody looked", not "the amplifier was fine".
`source.parameters.clip_measured` is the only field that tells them apart,
and an entry without it is reported as UNKNOWN and kept out of every loss
total rather than being counted clean.

RUN IT
------
    python tools\\clipping_loss.py                 # table + figure
    python tools\\clipping_loss.py --no-figure     # table only
    python tools\\clipping_loss.py --out docs      # where the .png goes
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import coupling, histo, probes, sessreg  # noqa: E402
from backend import store as storemod                 # noqa: E402

LOGS = os.path.join(APP, "GUI_logs")
BANK_DIR = os.path.join(LOGS, "event_bank")

#: The four windows, from Spark, so there is one source for them. `cue1`
#: and `cue2` are the two the coupling is actually computed in, which is
#: why they are worth more than `pre` and `post`.
WINDOWS = list(coupling.CLIP_WINDOW_NAMES)
CUE_WINDOWS = ("cue1", "cue2")

REGIONS = probes.DEWEY_REGIONS
REGION_ORDER = list(probes.DEWEY_NETWORK_ORDER)
N_REGIONS = len(REGIONS)
N_PAIRS = len(coupling.region_pairs(REGION_ORDER))      # 66
N_CHANNELS = probes.DEWEY_SIZE                          # 32


# --------------------------------------------------------------------------
# Reading the bank
# --------------------------------------------------------------------------
def bank_entries(pattern="dewey_*.json"):
    """Every banked DEWEY entry, as (filename, parsed dict)."""
    out = []
    for path in sorted(glob.glob(os.path.join(BANK_DIR, pattern))):
        with open(path, "r", encoding="utf-8") as fh:
            out.append((os.path.basename(path), json.load(fh)))
    return out


def measured_state(entry):
    """Was clipping actually measured before this was banked?

    Three answers, not two. `True` means the check ran. `False` means it
    demonstrably did not. `None` means the entry does not carry the field
    at all, which is older still and equally not a clean amplifier.
    """
    params = ((entry.get("source") or {}).get("parameters") or {})
    if "clip_measured" not in params:
        return None
    return bool(params["clip_measured"])


def raw_channel_blocks(entry):
    """Channel-blocks straight off the JSON -- the INDEPENDENT pass.

    One block is (event, window, channel). A channel on both the measured
    list and the decided list in one window is ONE block, not two, which is
    the same rule `web/js/eventbank.js exclusionSummary` states out loud.

    Deliberately does not call anything in `coupling`: this exists to be
    compared against the number that does.
    """
    total = 0
    per_window = defaultdict(int)
    measured = decided = both = 0
    channels = defaultdict(int)
    saw_flat = False
    for ev in (entry.get("events") or []):
        lists = {}
        # `kept` is what a person overruled back in, in Clean, against the
        # measurement. A kept block is not lost, so it comes out of the
        # count -- the same subtraction `coupling.excluded_for` makes. With
        # no `kept` this is exactly the old union.
        for key in ("clipped", "excluded", "kept"):
            got = ev.get(key)
            if isinstance(got, dict):
                lists[key] = {str(w): {int(c) for c in (v or [])}
                              for w, v in got.items()}
            elif got:
                saw_flat = True
                flat = {int(c) for c in got}
                lists[key] = {w: set(flat) for w in WINDOWS}
            else:
                lists[key] = {}
        for w in WINDOWS:
            m = lists["clipped"].get(w) or set()
            d = lists["excluded"].get(w) or set()
            k = lists["kept"].get(w) or set()
            for c in ((m | d) - k):
                total += 1
                per_window[w] += 1
                channels[c] += 1
                if c in m and c in d:
                    both += 1
                elif c in m:
                    measured += 1
                else:
                    decided += 1
    return {"blocks": total, "by_window": dict(per_window),
            "measured_only": measured, "decided_only": decided,
            "both": both, "by_channel": dict(channels), "flat": saw_flat}


# --------------------------------------------------------------------------
# The accounting, through coupling.py
# --------------------------------------------------------------------------
def entry_loss(entry, bad=(), present=None, probe=None):
    """One banked entry, walked up the ladder.

    Everything below comes out of `coupling.channel_sanity` and
    `coupling.blocked_pairs`. Three passes over the same events, because
    three different questions are being asked and merging them would make
    the histology invisible inside the clipping:

      clip   bad channels + clipping, no histology   -- what saturation cost
      hist   histology only, nothing clipped         -- what the probes cost
      both   everything at once                      -- what is actually left
    """
    events = entry.get("events") or []
    n_ev = len(events)

    out = {
        "n_events": n_ev,
        # channel-blocks, via coupling.excluded_for -- the SECOND derivation
        "channel_blocks": 0,
        "channel_blocks_by_window": defaultdict(int),
        # region-blocks and pair-blocks, per cause
        "region_blocks": defaultdict(int),        # cause -> n
        "pair_blocks": defaultdict(int),
        "region_by_window": {c: defaultdict(int)
                             for c in ("clip", "hist", "both")},
        "pair_by_window": {c: defaultdict(int)
                           for c in ("clip", "hist", "both")},
        # region-blocks per region name, clipping only
        "region_named": defaultdict(int),
        "region_named_hist": defaultdict(int),
        "windows_seen": set(),
        "off_montage": set(),
    }

    # Histology is a fact about the rat, not about the event, so it is
    # computed once and its cost is n_events * n_windows * (what it blocks).
    hist_sanity = coupling.channel_sanity(
        REGIONS, bad=bad, clipped_by_window={}, windows=WINDOWS,
        present=present, probe=probe)
    hist_blocked_regions = [r for r in hist_sanity
                            if r["windows"][WINDOWS[0]]["channel"] is None]
    hist_pairs_per_window = {
        w: len(coupling.blocked_pairs(hist_sanity, w)) for w in WINDOWS}

    for ev in events:
        ex = coupling.excluded_for(ev)
        # `excluded_for` returns a dict when the event names windows and a
        # flat list when it does not; a flat list means every window, which
        # is what it has always meant.
        if isinstance(ex, dict):
            per = {w: set(ex.get(w) or ()) for w in WINDOWS}
            out["windows_seen"] |= {w for w, v in ex.items() if v}
        else:
            per = {w: set(ex) for w in WINDOWS}
            if ex:
                out["windows_seen"] |= set(WINDOWS)
        for w in WINDOWS:
            out["channel_blocks"] += len(per[w])
            out["channel_blocks_by_window"][w] += len(per[w])
            out["off_montage"] |= {c for c in per[w] if c > N_CHANNELS}

        san_clip = coupling.channel_sanity(
            REGIONS, bad=bad, clipped_by_window=ex, windows=WINDOWS,
            present=present, probe=None)
        san_both = coupling.channel_sanity(
            REGIONS, bad=bad, clipped_by_window=ex, windows=WINDOWS,
            present=present, probe=probe)

        for cause, san in (("clip", san_clip), ("both", san_both)):
            for w in WINDOWS:
                gone = [r for r in san if r["windows"][w]["channel"] is None]
                out["region_blocks"][cause] += len(gone)
                out["region_by_window"][cause][w] += len(gone)
                if cause == "clip":
                    for r in gone:
                        out["region_named"][r["region"]] += 1
                npairs = len(coupling.blocked_pairs(san, w))
                out["pair_blocks"][cause] += npairs
                out["pair_by_window"][cause][w] += npairs
        for w in WINDOWS:
            out["region_blocks"]["hist"] += len(hist_blocked_regions)
            out["region_by_window"]["hist"][w] += len(hist_blocked_regions)
            out["pair_blocks"]["hist"] += hist_pairs_per_window[w]
            out["pair_by_window"]["hist"][w] += hist_pairs_per_window[w]
            for r in hist_blocked_regions:
                out["region_named_hist"][r["region"]] += 1

    out["hist_blocked_regions"] = [r["region"] for r in hist_blocked_regions]
    return out


def pair_identity_holds(n_blocked_regions, n_blocked_pairs, n_regions=None):
    """A pair is blocked iff either side is -- so the count is forced.

    With `b` of `n` regions gone, the pairs that survive are the ones drawn
    from the `n - b` that remain, so

        blocked = C(n, 2) - C(n - b, 2)

    Nothing in this file computes `n_blocked_pairs`; `coupling.blocked_pairs`
    does. This checks its answer against arithmetic that cannot be wrong for
    a different reason than the code is.
    """
    n = N_REGIONS if n_regions is None else n_regions
    left = n - n_blocked_regions
    expect = (n * (n - 1) // 2) - (left * (left - 1) // 2)
    return expect == n_blocked_pairs, expect


# --------------------------------------------------------------------------
# Putting it together
# --------------------------------------------------------------------------
def analyse():
    store = storemod.Store(LOGS, auto_stage=False)
    reg = sessreg.Registry(store)
    # One index off one read. `Registry.by_gid` re-stats every shard on
    # every call, which is most of a second each and there are 33 of them.
    by_gid = {r.get("gid"): r for r in reg.all()}

    entries = bank_entries()
    rows, unknown, problems = [], [], []
    hist_cache = {}

    for fname, entry in entries:
        rat = entry.get("mouse")
        gid = entry.get("gid")
        rec = by_gid.get(gid) or {}
        bad_all = sorted(int(c) for c in (rec.get("bad_channels") or []))
        # Only bad channels the montage actually uses can eat redundancy.
        # J3's recordings are 64-channel files with 33-64 marked bad, and
        # not one of those is in any DEWEY region.
        bad = [c for c in bad_all if c <= N_CHANNELS]
        n_ch = rec.get("n_channels")
        present = (set(range(1, int(n_ch) + 1)) if n_ch else None)

        state = measured_state(entry)
        raw = raw_channel_blocks(entry)

        if rat not in hist_cache:
            hist_cache[rat] = (histo.probe_sanity(rat, REGIONS)
                               if rat is not None else None)
        probe = hist_cache[rat]

        row = {
            "file": fname, "gid": gid, "rat": rat,
            "session": entry.get("session"),
            "label": entry.get("session_label") or entry.get("name"),
            "n_events": len(entry.get("events") or []),
            "measured": state,
            "bad_all": bad_all, "bad_in_montage": bad,
            "n_channels": n_ch,
            "raw": raw,
        }
        if state is not True:
            row["loss"] = None
            unknown.append(row)
            rows.append(row)
            continue

        loss = entry_loss(entry, bad=bad, present=present, probe=probe)
        row["loss"] = loss
        if loss["channel_blocks"] != raw["blocks"]:
            problems.append(
                "%s: channel-blocks disagree -- raw JSON pass %d, "
                "coupling.excluded_for pass %d"
                % (fname, raw["blocks"], loss["channel_blocks"]))
        rows.append(row)

    return {"rows": rows, "unknown": unknown, "problems": problems,
            "hist": hist_cache}


def totals(rows, causes=("clip", "hist", "both")):
    """Everything summed, in each unit, over the entries that were measured."""
    t = {
        "entries": 0, "events": 0,
        "channel_blocks": 0,
        "channel_by_window": defaultdict(int),
        "region_blocks": defaultdict(int),
        "pair_blocks": defaultdict(int),
        "region_by_window": {c: defaultdict(int) for c in causes},
        "pair_by_window": {c: defaultdict(int) for c in causes},
        "region_named": defaultdict(int),
        "region_named_hist": defaultdict(int),
        "by_rat": defaultdict(lambda: {
            "events": 0, "channel_blocks": 0,
            "region_blocks": defaultdict(int),
            "pair_blocks": defaultdict(int)}),
        "by_channel": defaultdict(int),
        "measured_only": 0, "decided_only": 0, "both_lists": 0,
    }
    for r in rows:
        loss = r.get("loss")
        if not loss:
            continue
        t["entries"] += 1
        t["events"] += loss["n_events"]
        t["channel_blocks"] += loss["channel_blocks"]
        for w, n in loss["channel_blocks_by_window"].items():
            t["channel_by_window"][w] += n
        for c in causes:
            t["region_blocks"][c] += loss["region_blocks"][c]
            t["pair_blocks"][c] += loss["pair_blocks"][c]
            for w in WINDOWS:
                t["region_by_window"][c][w] += loss["region_by_window"][c][w]
                t["pair_by_window"][c][w] += loss["pair_by_window"][c][w]
        for name, n in loss["region_named"].items():
            t["region_named"][name] += n
        for name, n in loss["region_named_hist"].items():
            t["region_named_hist"][name] += n
        for c, n in r["raw"]["by_channel"].items():
            t["by_channel"][c] += n
        t["measured_only"] += r["raw"]["measured_only"]
        t["decided_only"] += r["raw"]["decided_only"]
        t["both_lists"] += r["raw"]["both"]
        k = t["by_rat"][r["rat"]]
        k["events"] += loss["n_events"]
        k["channel_blocks"] += loss["channel_blocks"]
        for c in causes:
            k["region_blocks"][c] += loss["region_blocks"][c]
            k["pair_blocks"][c] += loss["pair_blocks"][c]
    return t


def redundancy(t):
    """Per region: did having more wires actually buy anything?

    Four wires only help if the four fail INDEPENDENTLY. If a wire clips
    with probability p and the wires are independent, a four-wire region
    goes dark with probability p^4 and a two-wire one with p^2. Comparing
    that prediction against what actually happened is the whole question:
    a region whose observed rate is orders of magnitude above the
    prediction is a region whose wires all saturate together, and its
    redundancy is nominal.

    Returns one record per region, in network order.
    """
    per_wire_d = t["events"] * len(WINDOWS)     # blocks a single wire could lose
    by_name = {r["region"]: r for r in REGIONS}
    out = []
    for name in REGION_ORDER:
        csc = by_name[name]["csc"]
        rates = [t["by_channel"].get(c, 0) / float(per_wire_d or 1)
                 for c in csc]
        indep = 1.0
        for p in rates:
            indep *= p
        obs = t["region_named"].get(name, 0) / float(per_wire_d or 1)
        out.append({
            "region": name, "n_wires": len(csc), "csc": list(csc),
            "wire_rates": rates,
            "mean_wire_rate": sum(rates) / len(rates),
            "observed": obs,
            "independent": indep,
            # How many times more often the region actually went dark than
            # independent wires would have made it. Capped for printing
            # when the prediction is zero.
            "ratio": (obs / indep) if indep > 0 else None,
        })
    return out


def denominators(n_events, n_windows=None):
    nw = len(WINDOWS) if n_windows is None else n_windows
    return {
        "channel": n_events * nw * N_CHANNELS,
        "region": n_events * nw * N_REGIONS,
        "pair": n_events * nw * N_PAIRS,
    }


def pct(n, d):
    return (100.0 * n / d) if d else 0.0


# --------------------------------------------------------------------------
# Printing -- every number the figure draws, and a few it does not
# --------------------------------------------------------------------------
def report(res, t):
    rows, unknown = res["rows"], res["unknown"]
    d = denominators(t["events"])
    say = print

    say("")
    say("=" * 74)
    say("DEWEY cue pairs: what the clipping actually cost")
    say("=" * 74)
    say("")
    rats = sorted({r["rat"] for r in rows})
    sess = sorted({r["session"] for r in rows})
    say("  %d banked entries, rats J%s" % (len(rows), ", J".join(
        str(x) for x in rats)))
    say("  sessions %s -- session n is Precon n (Con is 10+n, Test is 20+n),"
        % ", ".join(str(s) for s in sess))
    say("  so every entry here is a PRECONDITIONING SPC run. Conditioning and")
    say("  test sessions hold no cue pairs at all and are not in this bank.")
    say("")
    say("  %d entries carry a clipping measurement (%d cue pairs)."
        % (t["entries"], t["events"]))
    if unknown:
        say("  %d do NOT and are counted as UNKNOWN, never as clean:" % len(unknown))
        for r in unknown:
            say("      %s  (clip_measured=%r)" % (r["file"], r["measured"]))
    else:
        say("  0 entries are unmeasured: every one of them was checked.")
    say("")

    say("  THE UNITS, because the four numbers below are not comparable:")
    say("    channel-block  one cue pair, one window, one WIRE")
    say("    region-block   one cue pair, one window, one REGION with no")
    say("                   usable wire left (Left PER survives on any of")
    say("                   CSC 5, 6, 7, 8)")
    say("    pair-block     one cue pair, one window, one of the %d region"
        % N_PAIRS)
    say("                   pairs -- one cell of the connectivity matrix")
    say("")

    say("-" * 74)
    say("THE LADDER")
    say("-" * 74)
    fmt = "  %-42s %8s %10s"
    say(fmt % ("", "lost", "of"))
    say(fmt % ("channel-blocks (the bank's headline)",
               "%d" % t["channel_blocks"], "%d" % d["channel"])
        + "   %5.1f%%" % pct(t["channel_blocks"], d["channel"]))
    say(fmt % ("region-blocks, clipping + bad wires",
               "%d" % t["region_blocks"]["clip"], "%d" % d["region"])
        + "   %5.1f%%" % pct(t["region_blocks"]["clip"], d["region"]))
    say(fmt % ("pair-blocks, clipping + bad wires",
               "%d" % t["pair_blocks"]["clip"], "%d" % d["pair"])
        + "   %5.1f%%" % pct(t["pair_blocks"]["clip"], d["pair"]))
    say("")
    say(fmt % ("region-blocks, histology alone",
               "%d" % t["region_blocks"]["hist"], "%d" % d["region"])
        + "   %5.1f%%" % pct(t["region_blocks"]["hist"], d["region"]))
    say(fmt % ("pair-blocks, histology alone",
               "%d" % t["pair_blocks"]["hist"], "%d" % d["pair"])
        + "   %5.1f%%" % pct(t["pair_blocks"]["hist"], d["pair"]))
    say(fmt % ("pair-blocks, everything at once",
               "%d" % t["pair_blocks"]["both"], "%d" % d["pair"])
        + "   %5.1f%%" % pct(t["pair_blocks"]["both"], d["pair"]))
    say("")
    say("  Where clipping and histology are added separately they double-count")
    say("  the regions both ruin; 'everything at once' is the honest total and")
    say("  is what is actually left to compute.")
    say("")

    say("-" * 74)
    say("BY WINDOW  (cue1 and cue2 are the two the coupling is computed in)")
    say("-" * 74)
    say("  %-7s %14s %14s %14s %14s"
        % ("window", "channel-blk %", "region-blk %", "pair-blk %",
           "pair-blk % all"))
    dw = denominators(t["events"], 1)
    for w in WINDOWS:
        star = " *" if w in CUE_WINDOWS else "  "
        say("  %-5s%s %6d %6.1f%% %6d %6.1f%% %6d %6.1f%% %6d %6.1f%%"
            % (w, star,
               t["channel_by_window"][w], pct(t["channel_by_window"][w],
                                              dw["channel"]),
               t["region_by_window"]["clip"][w],
               pct(t["region_by_window"]["clip"][w], dw["region"]),
               t["pair_by_window"]["clip"][w],
               pct(t["pair_by_window"]["clip"][w], dw["pair"]),
               t["pair_by_window"]["both"][w],
               pct(t["pair_by_window"]["both"][w], dw["pair"])))
    say("  * the cue windows")
    say("")

    say("-" * 74)
    say("BY RAT")
    say("-" * 74)
    say("  %-5s %6s %10s %10s %10s %10s %s"
        % ("rat", "pairs", "chan-blk%", "reg-blk%", "pair-blk%",
           "histology", "probes lost to histology"))
    for rat in sorted(t["by_rat"]):
        k = t["by_rat"][rat]
        dr = denominators(k["events"])
        lost = sorted({r["intended"] for r in (res["hist"].get(rat) or [])
                       if not r.get("usable")})
        say("  J%-4s %6d %9.1f%% %9.1f%% %9.1f%% %9.1f%% %s"
            % (rat, k["events"],
               pct(k["channel_blocks"], dr["channel"]),
               pct(k["region_blocks"]["clip"], dr["region"]),
               pct(k["pair_blocks"]["clip"], dr["pair"]),
               pct(k["pair_blocks"]["hist"], dr["pair"]),
               ", ".join(lost) if lost else "none"))
    say("")

    say("-" * 74)
    say("BY REGION -- region-blocks from clipping, and the redundancy")
    say("-" * 74)
    say("  %-11s %5s %14s %9s   %s"
        % ("region", "wires", "region-blocks", "of", "% of its windows"))
    per_region_d = t["events"] * len(WINDOWS)
    for name in REGION_ORDER:
        n_csc = len([r for r in REGIONS if r["region"] == name][0]["csc"])
        n = t["region_named"].get(name, 0)
        say("  %-11s %5d %14d %9d   %8.1f%%"
            % (name, n_csc, n, per_region_d, pct(n, per_region_d)))
    say("")
    four = [r["region"] for r in REGIONS if len(r["csc"]) == 4]
    two = [r["region"] for r in REGIONS if len(r["csc"]) == 2]
    n4 = sum(t["region_named"].get(x, 0) for x in four)
    n2 = sum(t["region_named"].get(x, 0) for x in two)
    say("  four-wire regions (%s): %d region-blocks of %d  (%.1f%%)"
        % (", ".join(four), n4, per_region_d * len(four),
           pct(n4, per_region_d * len(four))))
    say("  two-wire  regions (%d of them): %d region-blocks of %d  (%.1f%%)"
        % (len(two), n2, per_region_d * len(two),
           pct(n2, per_region_d * len(two))))
    say("")

    say("-" * 74)
    say("DID THE REDUNDANCY BUY ANYTHING?")
    say("-" * 74)
    say("  If a region's wires saturated independently, a region-block would")
    say("  need all of them at once: p^4 for a four-wire region, p^2 for a")
    say("  two-wire one. 'x worse' is how many times more often it actually")
    say("  happened, and it is the measure of how together the wires fail.")
    say("")
    say("  %-11s %5s %10s %12s %12s %9s"
        % ("region", "wires", "wire-blk %", "if independent", "observed",
           "x worse"))
    red = redundancy(t)
    for r in red:
        say("  %-11s %5d %9.1f%% %11.3f%% %11.1f%% %9s"
            % (r["region"], r["n_wires"], 100 * r["mean_wire_rate"],
               100 * r["independent"], 100 * r["observed"],
               ("%.0f" % r["ratio"]) if r["ratio"] else "-"))
    say("")
    say("  A region-block needs every wire down in the SAME window. That it")
    say("  happens this much more often than chance is the finding: the wires")
    say("  of a region saturate together, so the extra wires are not extra")
    say("  chances -- they are the same chance, counted again.")
    say("")

    say("-" * 74)
    say("WHERE THE BLOCKS CAME FROM")
    say("-" * 74)
    say("  measured only (the amplifier saturated): %d channel-blocks"
        % t["measured_only"])
    say("  decided only  (somebody removed it):     %d channel-blocks"
        % t["decided_only"])
    say("  on both lists (one block, not two):      %d channel-blocks"
        % t["both_lists"])
    if t["measured_only"] == 0 and t["decided_only"] == 0:
        say("  Every block is on BOTH lists, which means nobody has removed a")
        say("  channel by hand that the amplifier had not already ruined: the")
        say("  'decided' column is a copy of the measurement, not a second")
        say("  opinion. There is no human curation in these numbers yet.")
    worst = sorted(t["by_channel"].items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    say("  worst wires: " + ", ".join(
        "CSC %d (%d)" % (c, n) for c, n in worst))
    say("")

    say("  Bad channels, from the session registry: ")
    any_bad = False
    for r in rows:
        if r["bad_all"]:
            any_bad = True
            say("    %s  marked bad %d–%d, of which %d are in the DEWEY "
                "montage" % (r["file"], min(r["bad_all"]), max(r["bad_all"]),
                             len(r["bad_in_montage"])))
    if not any_bad:
        say("    none recorded on any of these recordings.")
    say("    Bad wires eat redundancy before clipping does, so they matter --")
    say("    but none of the ones recorded here is a channel any region uses.")
    say("")
    return d


def crosscheck(res, t):
    """Two derivations of every headline, printed as a pass/fail list."""
    ok = True
    print("-" * 74)
    print("CROSS-CHECKS")
    print("-" * 74)

    raw_total = sum(r["raw"]["blocks"] for r in res["rows"] if r.get("loss"))
    good = raw_total == t["channel_blocks"]
    ok &= good
    print("  [%s] channel-blocks: raw-JSON pass %d == coupling.excluded_for "
          "pass %d" % ("ok" if good else "FAIL", raw_total,
                       t["channel_blocks"]))

    for msg in res["problems"]:
        ok = False
        print("  [FAIL] " + msg)

    wsum = sum(t["channel_by_window"].values())
    good = wsum == t["channel_blocks"]
    ok &= good
    print("  [%s] per-window channel-blocks sum to the total (%d)"
          % ("ok" if good else "FAIL", wsum))

    rsum = sum(t["region_named"].values())
    good = rsum == t["region_blocks"]["clip"]
    ok &= good
    print("  [%s] per-region region-blocks sum to the total (%d vs %d)"
          % ("ok" if good else "FAIL", rsum, t["region_blocks"]["clip"]))

    # The pair count is forced by the region count, per window, per event.
    # Checked on every measured entry's every event rather than on the
    # totals, because totals of a non-linear identity need not agree.
    bad_id = identity_pass(res)
    good = bad_id == 0
    ok &= good
    print("  [%s] blocked pairs == C(12,2) - C(12-blocked,2) on every "
          "event x window (%d disagreements)"
          % ("ok" if good else "FAIL", bad_id))

    n = len(bank_entries())
    good = n == len(res["rows"])
    ok &= good
    print("  [%s] every bank entry on disk was read (%d)"
          % ("ok" if good else "FAIL", n))
    print("")
    return ok


def identity_pass(res):
    """Re-run the sanity for a sample and check the pair identity.

    Cheap because it only needs the two counts, and it is a real second
    derivation: `blocked_pairs` walks 66 pairs and this walks none.
    """
    store = storemod.Store(LOGS, auto_stage=False)
    reg = sessreg.Registry(store)
    by_gid = {r.get("gid"): r for r in reg.all()}
    bad_n = 0
    for r in res["rows"]:
        if not r.get("loss"):
            continue
        rec = by_gid.get(r["gid"]) or {}
        bad = [c for c in (rec.get("bad_channels") or []) if c <= N_CHANNELS]
        n_ch = rec.get("n_channels")
        present = set(range(1, int(n_ch) + 1)) if n_ch else None
        probe = res["hist"].get(r["rat"])
        with open(os.path.join(BANK_DIR, r["file"]), encoding="utf-8") as fh:
            entry = json.load(fh)
        for ev in (entry.get("events") or []):
            ex = coupling.excluded_for(ev)
            san = coupling.channel_sanity(
                REGIONS, bad=bad, clipped_by_window=ex, windows=WINDOWS,
                present=present, probe=probe)
            for w in WINDOWS:
                b = len([x for x in san if x["windows"][w]["channel"] is None])
                good, _ = pair_identity_holds(
                    b, len(coupling.blocked_pairs(san, w)))
                if not good:
                    bad_n += 1
    return bad_n


# --------------------------------------------------------------------------
# The figure
# --------------------------------------------------------------------------
# Four panels, because the argument has four steps and a single chart of
# four different units would be the thing this whole exercise is against.
#
# Colour: the region panel uses `probes.DEWEY_REGION_COLORS`, which is the
# app's anatomical key and is literal for the same reason an atlas is -- POR
# is that blue here, on the cluster and in the published figure, or the three
# cannot be read against one another. Everything else uses one hue per unit,
# assigned in fixed order and never cycled.
UNIT_COLOR = {
    "channel": "#2a78d6",     # slot 1
    "region": "#eb6834",      # slot 2
    "pair": "#1baf7a",        # slot 3
}
HIST_COLOR = "#4a3aa7"        # slot 7 -- a different CAUSE, not a fourth unit
INK = "#22252b"
MUTED = "#6b7280"
GRID = "#dfe3ea"


def figure(res, t, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = denominators(t["events"])
    dw = denominators(t["events"], 1)

    import textwrap

    fig = plt.figure(figsize=(15.0, 10.6), dpi=170)
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(2, 2, hspace=0.78, wspace=0.26,
                          left=0.145, right=0.985, top=0.805, bottom=0.115)

    fig.suptitle("DEWEY cue pairs: the loss is real, the headline is not",
                 x=0.043, ha="left", y=0.975, fontsize=18, color=INK,
                 fontweight="bold")
    fig.text(0.043, 0.935,
             "%d banked entries (rats J3–J11, Precon SPC runs only), "
             "%d cue pairs, four windows each. A block is one cue pair, in "
             "one window, on one wire — so a lost wire is not a lost"
             % (len(res["rows"]), t["events"]),
             ha="left", fontsize=10.6, color=MUTED)
    fig.text(0.043, 0.912,
             "region, and a lost region is not a lost matrix cell. Each "
             "panel names its own unit, and no panel shares a denominator "
             "with another.",
             ha="left", fontsize=10.6, color=MUTED)

    def dress(ax, title, sub=None, wrap=62):
        lines = 0
        if sub:
            sub = textwrap.fill(sub, wrap)
            lines = sub.count("\n") + 1
        ax.set_title(title, loc="left", fontsize=12.5, color=INK,
                     fontweight="bold", pad=10 + 12.6 * lines)
        if sub:
            ax.annotate(sub, xy=(0, 1.0), xytext=(0, 7),
                        xycoords="axes fraction", textcoords="offset points",
                        fontsize=9.3, color=MUTED, ha="left", va="bottom",
                        linespacing=1.35)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=MUTED, labelsize=9.5, length=3)
        for lab in ax.get_xticklabels() + ax.get_yticklabels():
            lab.set_color(INK)

    # -- A: the ladder -----------------------------------------------------
    ax = fig.add_subplot(gs[0, 0])
    steps = [
        ("channel-blocks lost\nthe bank's headline",
         t["channel_blocks"], d["channel"], UNIT_COLOR["channel"]),
        ("region-blocks lost\nafter wire redundancy",
         t["region_blocks"]["clip"], d["region"], UNIT_COLOR["region"]),
        ("region-PAIR-blocks lost\none blank cell of the matrix",
         t["pair_blocks"]["clip"], d["pair"], UNIT_COLOR["pair"]),
        ("pair-blocks: HISTOLOGY alone\nno amplifier involved",
         t["pair_blocks"]["hist"], d["pair"], HIST_COLOR),
        ("pair-blocks: both causes at once\nwhat is really blocked",
         t["pair_blocks"]["both"], d["pair"], "#22252b"),
    ]
    vals = [pct(n, dd) for _, n, dd, _ in steps]
    y = [len(steps) - 1 - i for i in range(len(steps))]
    ax.barh(y, vals, height=0.5,
            color=[c for _, _, _, c in steps], zorder=3)
    for i, (lab, n, dd, _c) in enumerate(steps):
        ax.text(vals[i] + 0.7, y[i],
                "%.1f%%   %s of %s"
                % (vals[i], "{:,}".format(n), "{:,}".format(dd)),
                va="center", fontsize=9.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([lab for lab, _, _, _ in steps], fontsize=9.3,
                       linespacing=1.3)
    # Above this line the cause is the amplifier; below it, the probe.
    ax.axhline(1.5, color=GRID, lw=1.1, zorder=1)
    ax.set_xlim(0, max(vals) * 1.72)
    ax.set_ylim(-0.6, len(steps) - 0.4)
    ax.set_xlabel("% of everything that could have been lost, in that unit",
                  fontsize=9.5, color=MUTED)
    ax.xaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    dress(ax, "The ladder of honest numbers",
          "Each bar is a different unit with its own denominator — they "
          "do not add up, and the ladder does not only go down: one blocked "
          "region of twelve blanks eleven of the sixty-six cells.")

    # -- B: by window ------------------------------------------------------
    ax = fig.add_subplot(gs[0, 1])
    xs = list(range(len(WINDOWS)))
    w = 0.26
    series = [
        ("channel-blocks", UNIT_COLOR["channel"],
         [pct(t["channel_by_window"][k], dw["channel"]) for k in WINDOWS]),
        ("region-blocks", UNIT_COLOR["region"],
         [pct(t["region_by_window"]["clip"][k], dw["region"])
          for k in WINDOWS]),
        ("pair-blocks", UNIT_COLOR["pair"],
         [pct(t["pair_by_window"]["clip"][k], dw["pair"]) for k in WINDOWS]),
    ]
    for i, (name, col, vals) in enumerate(series):
        off = (i - 1) * (w + 0.015)
        ax.bar([x + off for x in xs], vals, width=w, color=col, zorder=3,
               label=name, edgecolor="white", linewidth=0.8)
        for x, v in zip(xs, vals):
            ax.text(x + off, v + 0.35, "%.0f" % v, ha="center", va="bottom",
                    fontsize=8.2, color=INK)
    ax.set_xticks(xs)
    ax.set_xticklabels(["pre", "cue 1", "cue 2", "post"], fontsize=10)
    for i, k in enumerate(WINDOWS):
        if k in CUE_WINDOWS:
            ax.get_xticklabels()[i].set_fontweight("bold")
            ax.get_xticklabels()[i].set_color(INK)
    ax.set_ylabel("% lost in that window", fontsize=9.5, color=MUTED)
    ax.yaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.set_ylim(0, max(max(v) for _, _, v in series) * 1.28)
    ax.legend(frameon=False, fontsize=9.3, loc="upper left",
              ncol=3, handlelength=1.1, columnspacing=1.2,
              labelcolor=INK)
    dress(ax, "By window — clipping only",
          "cue 1 and cue 2 (bold) are the windows the coupling is "
          "computed in; losing those costs the result.")

    # -- C: by rat ---------------------------------------------------------
    ax = fig.add_subplot(gs[1, 0])
    rats = sorted(t["by_rat"])
    xs = list(range(len(rats)))
    w = 0.38
    clip_v, hist_v = [], []
    for rat in rats:
        k = t["by_rat"][rat]
        dr = denominators(k["events"])
        clip_v.append(pct(k["pair_blocks"]["clip"], dr["pair"]))
        hist_v.append(pct(k["pair_blocks"]["hist"], dr["pair"]))
    ax.bar([x - w / 2 - 0.008 for x in xs], clip_v, width=w,
           color=UNIT_COLOR["pair"], zorder=3, label="clipping + bad wires",
           edgecolor="white", linewidth=0.8)
    # A rat with no row in the workbook is EXCLUDED, by decision
    # (backend/histo.py, USABLE), not found to have missed. Its bar is the
    # real cost -- nothing of it is computed -- but it must not look like a
    # finding, so it is drawn hatched and hollow, and the solid bars are
    # only the rats somebody actually scored.
    solid = [0.0 if not histo.scored(r) else v for r, v in zip(rats, hist_v)]
    ax.bar([x + w / 2 + 0.008 for x in xs], solid, width=w,
           color=HIST_COLOR, zorder=3, label="histology (probe missed)",
           edgecolor="white", linewidth=0.8)
    unsc = [(x, v) for x, r, v in zip(xs, rats, hist_v)
            if not histo.scored(r)]
    if unsc:
        ax.bar([x + w / 2 + 0.008 for x, _v in unsc], [v for _x, v in unsc],
               width=w, facecolor="none", edgecolor=HIST_COLOR, hatch="///",
               linewidth=1.0, zorder=3, label="excluded until scored")
    hi = max(clip_v + hist_v) or 1.0
    for x, v in zip(xs, clip_v):
        if v > hi * 0.12:
            ax.text(x - w / 2 - 0.008, v + hi * 0.02, "%.0f" % v,
                    ha="center", va="bottom", fontsize=8.2, color=INK)
    for x, rat, v in zip(xs, rats, hist_v):
        # A rat with no row in the workbook has a zero here that means
        # "nobody has looked", which is not the same claim as "nothing
        # found" and must not be drawn as one.
        if not histo.scored(rat):
            ax.text(x + w / 2 + 0.008, v * 0.5, "not scored",
                    ha="center", va="center", rotation=90, fontsize=8.6,
                    color=HIST_COLOR,
                    bbox=dict(boxstyle="round,pad=0.18", fc="white",
                              ec="none"))
            continue
        ax.text(x + w / 2 + 0.008, v + hi * 0.02, "%.0f" % v,
                ha="center", va="bottom", fontsize=8.2, color=INK)
    ax.set_xticks(xs)
    ax.set_xticklabels(["J%d" % r for r in rats], fontsize=10)
    ax.set_ylabel("% of matrix cells blocked (pair-blocks)",
                  fontsize=9.5, color=MUTED)
    ax.yaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.set_ylim(0, hi * 1.2)
    ax.legend(frameon=False, fontsize=9.3, loc="upper left", ncol=2,
              handlelength=1.1, labelcolor=INK)
    no_hist = [r for r in rats if not histo.scored(r)]
    clean = [r for r in rats if histo.scored(r)
             and not any(not x.get("usable") for x in (res["hist"][r] or []))]
    dress(ax, "By rat — pair-blocks, the unit that costs a matrix cell",
          "Two separate causes, never added: a pair ruined by both is one "
          "blank cell."
          + (" J%s really do lose nothing to histology — every probe "
             "of theirs that moved landed somewhere that can still be "
             "named." % ", J".join(str(r) for r in clean) if clean else "")
          + (" J%s has no row in the workbook and is excluded until it is "
             "scored (hatched) -- a decision, not a finding."
             % ", J".join(str(r) for r in no_hist) if no_hist else ""))

    # -- D: by region, grouped by how much redundancy it has ---------------
    ax = fig.add_subplot(gs[1, 1])
    red = redundancy(t)
    # Grouped by wire count rather than by the ring order, because the
    # asymmetry IS the panel: four wires on the left, two on the right.
    red = sorted(red, key=lambda r: (-r["n_wires"],
                                     REGION_ORDER.index(r["region"])))
    names = [r["region"] for r in red]
    vals = [100 * r["observed"] for r in red]
    pred = [100 * r["independent"] for r in red]
    cols = [probes.DEWEY_REGION_COLORS[n] for n in names]
    xs = list(range(len(names)))
    ax.bar(xs, vals, width=0.7, color=cols, zorder=3,
           edgecolor="white", linewidth=0.9, label="actually blocked")
    ax.scatter(xs, pred, marker="_", s=260, linewidths=2.2, color=INK,
               zorder=5, label="if its wires failed independently")
    top = max(vals) * 1.45
    for x, v in zip(xs, vals):
        ax.text(x, v + top * 0.02, "%.0f%%" % v, ha="center", va="bottom",
                fontsize=8.2, color=INK)
    n_four = sum(1 for r in red if r["n_wires"] == 4)
    ax.axvline(n_four - 0.5, color=GRID, lw=1.2, zorder=1)
    # Under the axis, so the legend has the top of the panel to itself.
    blend = ("data", "axes fraction")
    for lo, hi, say_it in ((-0.4, n_four - 0.6, "four wires each"),
                           (n_four - 0.4, len(names) - 0.6,
                            "two wires each")):
        ax.annotate("", xy=(lo, -0.33), xytext=(hi, -0.33),
                    xycoords=blend, textcoords=blend, annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.9))
        ax.annotate(say_it, xy=((lo + hi) / 2.0, -0.375), xycoords=blend,
                    ha="center", va="top", fontsize=9.4, color=MUTED,
                    annotation_clip=False)
    ax.set_xticks(xs)
    ax.set_xticklabels(names, rotation=38, ha="right", fontsize=8.8)
    ax.set_ylabel("% of its windows with no usable wire left",
                  fontsize=9.5, color=MUTED)
    ax.yaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.set_ylim(0, top)
    ax.set_xlim(-0.7, len(names) - 0.3)
    ax.legend(frameon=False, fontsize=9.3, loc="upper left", ncol=1,
              handlelength=1.3, labelcolor=INK, borderpad=0.1,
              handletextpad=0.6)
    dress(ax, "Redundancy that is not there",
          "The four-wire regions go dark MORE often than the two-wire "
          "ones. Their wires saturate together, so the spares are the "
          "same failure counted again.")

    fig.savefig(out_path, facecolor="white")
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(APP, "docs"),
                    help="where the figure goes (default: docs/)")
    ap.add_argument("--name", default="dewey-clipping-loss.png")
    ap.add_argument("--no-figure", action="store_true")
    ap.add_argument("--json", default=None,
                    help="also write the totals as JSON here")
    args = ap.parse_args(argv)

    res = analyse()
    t = totals(res["rows"])
    report(res, t)
    ok = crosscheck(res, t)

    if not args.no_figure:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, args.name)
        figure(res, t, path)
        print("figure -> %s" % path)

    if args.json:
        d = denominators(t["events"])
        blob = {
            "entries": len(res["rows"]), "measured": t["entries"],
            "unknown": [r["file"] for r in res["unknown"]],
            "events": t["events"], "denominators": d,
            "channel_blocks": t["channel_blocks"],
            "region_blocks": dict(t["region_blocks"]),
            "pair_blocks": dict(t["pair_blocks"]),
            "by_window": {
                "channel": dict(t["channel_by_window"]),
                "region_clip": dict(t["region_by_window"]["clip"]),
                "pair_clip": dict(t["pair_by_window"]["clip"]),
                "pair_both": dict(t["pair_by_window"]["both"]),
            },
            "by_region_clip": dict(t["region_named"]),
        }
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(blob, fh, indent=1, sort_keys=True)
        print("totals -> %s" % args.json)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
