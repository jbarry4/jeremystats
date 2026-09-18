"""
check_braces.py -- the alignment rule, against cases worked out by hand.

The rule in `braces.assign` is the whole of Braces that can be wrong without
anybody noticing. A misread channel announces itself: the shift histogram
goes flat and the counts collapse. A subtly wrong ASSIGNMENT produces a set
that looks perfect and has two events swapped, or one event quietly stranded
on every burst in the recording.

So the cases here are not a smoke test. Each one is a situation the naive
implementation gets wrong, with the answer worked out by hand and written
down beside it.

Run it:  python -m tools.check_braces        (from the BARRY GUI folder)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import braces                                   # noqa: E402

FAIL = []


def check(name, got, want, why=""):
    ok = got == want
    print("  %-4s %s" % ("ok" if ok else "FAIL", name))
    if not ok:
        print("       wanted %r" % (want,))
        print("       got    %r" % (got,))
        if why:
            print("       %s" % why)
        FAIL.append(name)


def near(name, got, want, tol=1e-9):
    ok = abs(got - want) <= tol
    print("  %-4s %s  (%.6f)" % ("ok" if ok else "FAIL", name, got))
    if not ok:
        print("       wanted %.6f" % want)
        FAIL.append(name)


print("\nTHE RULE")
print("-" * 68)

# ---------------------------------------------------------------------------
# The case this tool exists for.
#
#   peak A          stamp 1   peak B      stamp 2
#   27.800          27.894    27.920      27.955
#
# Nearest-peak-wins gives B to stamp 1 (26 ms) and strands stamp 2, because A
# is 155 ms behind it -- outside the window. The right answer moves stamp 1
# further, to A (94 ms), so stamp 2 can have B (35 ms).
# ---------------------------------------------------------------------------
stamps = [27.894, 27.955]
peaks = [27.800, 27.920]
check("the edge case: the first stamp takes the former peak",
      braces.assign(stamps, peaks, 100), [0, 1],
      "nearest-peak-wins would say [1, None] and lose a curated event")
check("...and nearest-peak-wins really would have said that",
      braces.greedy(stamps, peaks, 100), [1, None],
      "greedy takes B for stamp 1, leaving stamp 2 with nothing free")
check("...while `nearest` reports contention, not contention resolved",
      braces.nearest(stamps, peaks, 100), [1, 1],
      "both stamps are NEAREST to B -- that is what makes them contested")

# Mirrored in time. The same situation running the other way must give the
# mirrored answer -- if it does not, something in the DP has a direction.
stamps_m = [-27.955, -27.894]
peaks_m = [-27.920, -27.800]
check("the same case mirrored in time",
      braces.assign(stamps_m, peaks_m, 100), [0, 1])

# ---------------------------------------------------------------------------
# One peak, two stamps that can both reach it. The nearer one gets it; the
# other stays put rather than being dragged onto a peak it does not own.
# ---------------------------------------------------------------------------
check("two stamps, one peak: the nearer one takes it",
      braces.assign([10.000, 10.090], [10.005], 100), [0, None])
check("...and the other way round",
      braces.assign([9.910, 10.000], [10.005], 100), [None, 0])

# ---------------------------------------------------------------------------
# No crossing. Without the constraint, a solver minimising total distance
# alone would swap these -- 2 ms + 2 ms beats 96 ms + 96 ms -- and the two
# events would trade curation labels.
# ---------------------------------------------------------------------------
check("the assignment never crosses",
      braces.assign([10.000, 10.098], [10.002, 10.100], 100), [0, 1])

# ---------------------------------------------------------------------------
# Out of reach. A stamp with nothing within the window stays where it is,
# and does not reach past the window for the nearest thing there is.
# ---------------------------------------------------------------------------
check("a stamp with no peak in reach takes nothing",
      braces.assign([50.000], [50.101], 100), [None])
check("...and one exactly at the window edge does take it",
      braces.assign([50.000], [50.100], 100), [0])

# ---------------------------------------------------------------------------
# A chain. Three stamps and three peaks where every stamp is nearest to the
# peak of the one after it: greedy strands the last, the rule shifts all
# three back by one and matches everything.
# ---------------------------------------------------------------------------
check("a three-long chain resolves in one go",
      braces.assign([1.090, 1.190, 1.290], [1.000, 1.100, 1.200], 100),
      [0, 1, 2])
check("...which greedy would have got wrong",
      braces.greedy([1.090, 1.190, 1.290], [1.000, 1.100, 1.200], 100),
      [1, 2, None])

# ---------------------------------------------------------------------------
# More peaks than stamps, and more stamps than peaks.
# ---------------------------------------------------------------------------
check("spare peaks are simply not used",
      braces.assign([5.000], [4.950, 5.001, 5.060], 100), [1])
check("spare stamps are left alone, not stacked onto one peak",
      braces.assign([5.000, 5.010, 5.020], [5.011], 100), [None, 0, None])

# ---------------------------------------------------------------------------
# Runs. The whole reason this is fast: peaks 100 ms apart mean a stamp
# reaches at most three, and stamps far apart cannot interact at all.
# ---------------------------------------------------------------------------
got = list(braces.runs([1.0, 5.0, 9.0], [1.01, 5.01, 9.01], 0.1))
check("three isolated stamps are three runs", len(got), 3)
got = list(braces.runs([1.00, 1.05], [1.01, 1.06], 0.1))
check("two interacting stamps are one run", len(got), 1)

print("\nNO DUPLICATES, EVER")
print("-" * 68)
# The property that matters most and is easiest to lose: one peak per stamp.
# A greedy implementation puts both of these on 100.000 and the set acquires
# two events at an identical time.
out = braces.assign([99.960, 100.040], [100.000], 100)
check("two stamps never land on one peak",
      len([x for x in out if x == 0]), 1,
      "eventbank.DUP_DP is 0.1 ms -- two stamps on one peak is a duplicate")

# Over a pile of random-ish input: no peak used twice, order never crosses.
import random                                                # noqa: E402
random.seed(7)
bad_dupe = bad_order = 0
for trial in range(400):
    n = random.randint(1, 25)
    m = random.randint(1, 25)
    st = sorted(round(random.uniform(0, 5), 4) for _ in range(n))
    pk = sorted(round(random.uniform(0, 5), 4) for _ in range(m))
    pk = sorted(set(pk))
    got = braces.assign(st, pk, 100)
    used = [x for x in got if x is not None]
    if len(used) != len(set(used)):
        bad_dupe += 1
    if used != sorted(used):
        bad_order += 1
check("400 random sets: no peak taken twice", bad_dupe, 0)
check("400 random sets: nothing ever crosses", bad_order, 0)

print("\nIT REALLY IS OPTIMAL")
print("-" * 68)
# Brute force against the DP on small inputs. The DP is the only place the
# rule lives, so "it agrees with itself" proves nothing -- this enumerates
# every legal assignment and compares the objective directly.
import itertools                                             # noqa: E402


def brute(st, pk, window):
    best = None
    n, m = len(st), len(pk)
    for r in range(min(n, m), -1, -1):
        for si in itertools.combinations(range(n), r):
            for pi in itertools.combinations(range(m), r):
                # combinations are ascending in both, so pairing them in
                # order is the only non-crossing assignment of this choice.
                tot = 0.0
                ok = True
                for a, b in zip(si, pi):
                    d = abs(st[a] - pk[b])
                    if d > window:
                        ok = False
                        break
                    tot += d
                if not ok:
                    continue
                key = (n - r, round(tot, 9))
                if best is None or key < best[0]:
                    best = (key, si, pi)
    return best


random.seed(11)
worse = 0
for trial in range(250):
    n = random.randint(1, 6)
    m = random.randint(1, 6)
    st = sorted(round(random.uniform(0, 0.5), 4) for _ in range(n))
    pk = sorted(set(round(random.uniform(0, 0.5), 4) for _ in range(m)))
    got = braces.assign(st, pk, 100)
    mine_n = sum(1 for x in got if x is None)
    mine_d = round(sum(abs(st[i] - pk[j])
                       for i, j in enumerate(got) if j is not None), 9)
    ref = brute(st, pk, 0.1)
    if ref is None:
        continue
    if (mine_n, mine_d) > ref[0]:
        worse += 1
        if worse == 1:
            print("       first disagreement: stamps=%r peaks=%r" % (st, pk))
            print("       mine=%r (%d unmatched, %.6f)" % (got, mine_n, mine_d))
            print("       best=%r" % (ref,))
check("250 random sets match exhaustive search exactly", worse, 0)

print("\nTHE PROPOSAL")
print("-" * 68)
# The flags, on the edge case. Stamp 1 gave up a nearer peak, so it is
# contested; stamp 2 got what it wanted, so it is clean.
fake = {"times": [27.800, 27.920], "amps": [612.0, 840.0],
        "thr_uv": 434.0, "band": [5, 100], "n_channels": 64,
        "dist_ms": 100.0, "estimator": "sd", "lfp_fs": 1000.0}
out = braces.propose([{"start": 27.894}, {"start": 27.955}], fake, 100)
rows = out["rows"]
check("the contested stamp is flagged", rows[0]["flag"], "contested")
check("the stamp that got its own peak is not", rows[1]["flag"], None)
near("and it moved by -94 ms", rows[0]["shift_ms"], -94.0, 1e-6)
near("and the other by -35 ms", rows[1]["shift_ms"], -35.0, 1e-6)
check("both are counted as moved", out["n_moved"], 2)
check("and the summary says greedy would have stranded one",
      out["greedy_stranded"], 1)

# A weak peak: under what a detector would have called an event.
weak = dict(fake, times=[10.000], amps=[240.0])
out = braces.propose([{"start": 10.010}], weak, 100)
check("a peak under the detection threshold is flagged weak",
      out["rows"][0]["flag"], "weak")

# Near the edge.
far = dict(fake, times=[10.000], amps=[900.0])
out = braces.propose([{"start": 10.090}], far, 100)
check("a move past 80% of the window is flagged", out["rows"][0]["flag"],
      "edge")

# Nothing in reach.
out = braces.propose([{"start": 10.500}], far, 100)
check("a stamp with nothing in reach is flagged",
      out["rows"][0]["flag"], "no_peak")
check("...and does not move", out["rows"][0]["now"], 10.500)
check("...and is not counted as moved", out["rows"][0]["moved"], False)

# Already right. A stamp inside a millisecond of its peak is not a move.
out = braces.propose([{"start": 10.0004}], far, 100)
check("a stamp already on its peak is not a move",
      out["rows"][0]["same"], True)

# Unsorted input. A bank entry's order is whatever last wrote it.
jumbled = dict(fake, times=[1.000, 2.000], amps=[900.0, 900.0])
out = braces.propose([{"start": 2.010}, {"start": 1.010}], jumbled, 100)
back = {r["i"]: r["now"] for r in out["rows"]}
check("unsorted events still align to the right peaks",
      [back[0], back[1]], [2.000, 1.000])

print("\nA MOVE UNLIKE THE OTHERS")
print("-" * 68)
# The fixed edge rule is about the window and says nothing when a set's
# jitter is small. Measured on M8s9feb8: median 5.6 ms, largest 59.7, and at
# a 100 ms window not one of those trips an 80 ms edge -- so the one stamp
# that went sixty was confirmed silently along with the rest.
tight = {"times": [], "amps": [], "thr_uv": 1.0, "band": [5, 100],
         "n_channels": 64, "dist_ms": 100.0, "estimator": "sd",
         "lfp_fs": 1000.0}
evs = []
for i in range(30):
    # Thirty stamps 1 s apart, every one 5 ms early...
    tight["times"].append(round(10.0 + i, 3))
    tight["amps"].append(900.0)
    evs.append({"start": round(10.0 + i - 0.005, 3), "label_id": "spike"})
# ...except one, which is sixty early.
evs[17]["start"] = round(10.0 + 17 - 0.060, 3)
out = braces.propose(evs, tight, 100, align_ids={"spike"})
flags = [r["flag"] for r in out["rows"]]
check("the one that moved differently is flagged",
      flags[17], "outlier",
      "a 60 ms move in a set whose moves are all 5 ms is worth a look, and "
      "an 80 ms edge rule never sees it")
check("...and the twenty-nine that agree are not",
      [f for n, f in enumerate(flags) if n != 17], [None] * 29)
check("...and it is counted under its own reason",
      out["by_reason"], {"outlier": 1})

# A set with no spread at all must not flag everything: six MADs of nothing
# is nothing.
same = dict(tight, times=[round(10.0 + i, 3) for i in range(30)])
evs2 = [{"start": round(10.0 + i - 0.005, 3), "label_id": "spike"}
        for i in range(30)]
out = braces.propose(evs2, same, 100, align_ids={"spike"})
check("a set that all moved the same way flags nothing",
      out["n_flagged"], 0,
      "without a floor, six MADs of zero spread makes every stamp unusual")

print("\nONLY THE DENTATE SPIKES")
print("-" * 68)
# A curated set is not a list of events. It is a list of candidates, most of
# which are events and some of which somebody looked at and rejected. Moving
# a Garbage stamp asserts a position for something that is not there -- and,
# worse, one peak per stamp means it would TAKE the peak the real spike next
# to it needed.
one_peak = {"times": [50.000], "amps": [900.0], "thr_uv": 434.0,
            "band": [5, 100], "n_channels": 64, "dist_ms": 100.0,
            "estimator": "sd", "lfp_fs": 1000.0}
mixed = [
    # Garbage sits NEARER the peak, so nearest-peak-wins inside the run
    # would hand it over and strand the real spike.
    {"start": 50.004, "label_id": "garbage"},
    {"start": 50.030, "label_id": "spike"},
]
out = braces.propose(mixed, one_peak, 100, align_ids={"spike"})
check("a rejected stamp gets no row at all", len(out["rows"]), 1)
check("...and the row that is there is the real spike",
      out["rows"][0]["i"], 1)
check("...which keeps the peak the garbage was sitting closer to",
      round(out["rows"][0]["now"], 3), 50.000,
      "excluding it from the ANSWER is not enough -- it must not be able "
      "to compete for a peak in the first place")
check("...and what was left out is reported, not silently dropped",
      out["skipped"], {"garbage": 1})
check("...and counted", out["n_skipped"], 1)

# Undecided candidates are left alone too: nobody has said they are events.
out = braces.propose([{"start": 50.010}], one_peak, 100, align_ids={"spike"})
check("an undecided candidate is left alone", len(out["rows"]), 0)
check("...and named as undecided", out["skipped"], {"undecided": 1})

# A set with nothing alignable in it must still come back as a summary
# rather than half a dict the panel then reads fields off.
check("a set with no spikes in it still summarises", out["n"], 0)
truthy_hist = isinstance(out.get("hist"), list) and len(out["hist"]) == 20
check("...with a histogram the panel can draw", truthy_hist, True)

# Flags are NOT aligned: a flag means "come back to this", not "this is a
# dentate spike".
out = braces.propose([{"start": 50.010, "label_id": "flag"}],
                     one_peak, 100, align_ids={"spike"})
check("a flagged candidate is not aligned either", len(out["rows"]), 0)

print("\n" + "=" * 68)
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), ", ".join(FAIL)))
    sys.exit(1)
print("all checks passed")
