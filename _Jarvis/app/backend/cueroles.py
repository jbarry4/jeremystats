"""cueroles.py -- which of a rat's two cue pairs later gets food.

THE QUESTION
------------
DEWEY's preconditioning pairs two sounds, twice over: each rat hears two
ordered pairings (say Click -> Low Tone and Noise -> High tone) on every
Precon day. Conditioning then feeds after the SECOND cue of one pairing and
never after the other. So each rat has a "food pair" and a "no-food pair" --
and because the cohort is counterbalanced, the food pair is a different
pairing in every rat (arc_contracts.md 0a). Pooling across rats has to be by
ROLE, and the role has to be read off each rat's own conditioning, never
assumed from a table somebody typed.

HOW IT IS READ
--------------
From every Con SPC recording of the rat (registry: project DEWEY, phase
"Con", run "SPC"), `spark.read_events` gives the TTLs; mirrors and debounced
repeats are dropped exactly as Spark drops them. A cue presentation is
FOLLOWED when a "Pellet Delivery" TTL lands within `WINDOW_S` (15 s) after
its onset. The cue followed in any session is the food cue. Then:

  * no cue ever followed        -> CueRoleError (nobody was fed: no answer)
  * more than one cue followed  -> CueRoleError (ambiguous: never guessed)
  * the food cue closes exactly one of the rat's Precon pairings -> that is
    the food pair; every other pairing is no_food. Zero or two pairings
    closing on it -> CueRoleError.

"Ever followed" is deliberately the strictest reading: one pellet within
15 s of the other cue, in any session, is enough to refuse. The survey
(2026-09-29) found every rat unambiguous -- the other cue is followed 0 times.

WHAT IT RECORDS
---------------
`role_table(rat)` returns the food cue, the role of each pairing
(`roles: {cue_type: "food" | "no_food"}`) and its `source`: which Con
sessions were read, how often each cue was presented and followed, the
window, and the sessions skipped and why (a registry record called SPC whose
folder holds no cue at all is a misfiled FP run, and is said, not counted as
"no food"). `source` is deterministic -- no clock, no machine -- because it
travels into circuit payloads as `role_source`, and a timestamp there would
make every re-run a new version instead of a confirmation (0b).

Two registry records naming the SAME folder are read once (J9 Con3 has two
gids for one directory; counting it twice would double its pellets).
"""
from __future__ import annotations

import os
import re

from . import circuit, nlx, spark

#: A pellet this long after a cue's onset counts as following it. A cue is
#: ten seconds long and the rig feeds at or before its end (measured: the
#: latest pellet after a food cue is 10.25 s), so fifteen is generous without
#: reaching the next trial.
WINDOW_S = 15.0

FOOD_LABEL = "Pellet Delivery"
PROJECT = "DEWEY"
CON_PHASE = "Con"
PRECON_PHASE = "Precon"
RUN = "SPC"

RULE = ("a cue presentation is followed when a Pellet Delivery TTL lands "
        "within %g s after its onset; mirrors and debounced repeats are "
        "dropped as Spark drops them" % WINDOW_S)

ROLES = ("food", "no_food")


class CueRoleError(Exception):
    """The role of a rat's cue pairs cannot be read unambiguously. The
    message is a sentence for a person."""


# --------------------------------------------------------------------------
# Rats and records
# --------------------------------------------------------------------------
_RAT_RE = re.compile(r"^\s*[rRjJmM]?\s*0*(\d+)\s*$")


def rat_of(rat):
    """3, "3", "r3", "J3", "r003" -> 3."""
    if isinstance(rat, bool):
        raise CueRoleError("%r is not a rat." % (rat,))
    if isinstance(rat, int):
        return rat
    m = _RAT_RE.match(str(rat or ""))
    if not m:
        raise CueRoleError("%r is not a rat (say 3, r3 or J3)." % (rat,))
    return int(m.group(1))


def load_records(logs_dir=None):
    """Every session record, merged from its shards -- ONE read.

    `Registry.by_gid` re-stats every shard on each call; everything here
    works off one `all()` instead.
    """
    from . import sessreg
    from . import store as storemod
    if logs_dir is None:
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "GUI_logs")
    store = storemod.Store(logs_dir, auto_stage=False)
    return sessreg.Registry(store).all()


def records_for(rat, records, phase, run=RUN, project=PROJECT):
    """The rat's live records of one phase and run, in session order."""
    n = rat_of(rat)
    out = []
    for r in records or []:
        if r.get("retired"):
            continue
        if (r.get("project") or "") != project:
            continue
        if r.get("mouse") != n:
            continue
        if (r.get("phase") or "") != phase or (r.get("run") or "") != run:
            continue
        out.append(r)
    out.sort(key=lambda r: (r.get("phase_n") or 0, r.get("session") or 0,
                            r.get("gid") or ""))
    return out


def here_of(rec):
    """The first of the record's paths this machine can reach, or None."""
    from . import sessreg
    for p in rec.get("paths") or []:
        if sessreg.is_here(p):
            return p
    return None


def _folder_key(path):
    return os.path.normcase(os.path.normpath(str(path)))


# --------------------------------------------------------------------------
# The tally -- pure, and what the negative controls feed directly
# --------------------------------------------------------------------------
def usable(rows):
    """TTLs Spark counts: known codes, no mirrors, no bounces."""
    return [r for r in rows or []
            if r.get("known", True) and not r.get("is_mirror")
            and not r.get("debounced")]


def tally(rows, window_s=WINDOW_S):
    """One session: how often each cue was presented and followed by food.

    `rows`: `spark.read_events` rows (or anything with `label` and `t`).
    Returns {presented: {cue: n}, followed: {cue: n}, pellets: n,
    unclaimed: n, latency: {cue: [min, max]}} -- `followed` has a key for
    every presented cue, zero included, because "presented and never fed"
    is the fact the no-food role rests on.
    """
    rows = usable(rows)
    cues = [r for r in rows if r.get("label") in spark.CUES]
    pellets = sorted(float(r["t"]) for r in rows
                     if r.get("label") == FOOD_LABEL)
    presented, followed, lat = {}, {}, {}
    for c in cues:
        lab = c["label"]
        presented[lab] = presented.get(lab, 0) + 1
        followed.setdefault(lab, 0)
        t0 = float(c["t"])
        hits = [p - t0 for p in pellets if 0.0 < p - t0 <= window_s]
        if hits:
            followed[lab] += 1
            lo = min(hits)
            was = lat.get(lab)
            lat[lab] = [lo, lo] if was is None else [min(was[0], lo),
                                                     max(was[1], lo)]
    claimed = 0
    for p in pellets:
        if any(0.0 < p - float(c["t"]) <= window_s for c in cues):
            claimed += 1
    return {"presented": presented, "followed": followed,
            "pellets": len(pellets), "unclaimed": len(pellets) - claimed,
            "latency": {k: [round(v[0], 3), round(v[1], 3)]
                        for k, v in lat.items()}}


def combine(tallies):
    """Sum per-session tallies into one."""
    out = {"presented": {}, "followed": {}, "pellets": 0, "unclaimed": 0,
           "latency": {}}
    for t in tallies or []:
        for key in ("presented", "followed"):
            for cue, n in (t.get(key) or {}).items():
                out[key][cue] = out[key].get(cue, 0) + int(n)
        out["pellets"] += int(t.get("pellets") or 0)
        out["unclaimed"] += int(t.get("unclaimed") or 0)
        for cue, (lo, hi) in (t.get("latency") or {}).items():
            was = out["latency"].get(cue)
            out["latency"][cue] = [lo, hi] if was is None else [
                min(was[0], lo), max(was[1], hi)]
    return out


def _cue_order(cue):
    try:
        return spark.CUES.index(cue)
    except ValueError:
        return len(spark.CUES)


def food_cue_of(total, rat="this rat"):
    """The one cue ever followed by food, or CueRoleError."""
    fed = sorted((c for c, n in (total.get("followed") or {}).items() if n),
                 key=_cue_order)
    if not fed:
        heard = ", ".join("%s %d" % (c, n) for c, n in sorted(
            (total.get("presented") or {}).items(),
            key=lambda kv: _cue_order(kv[0]))) or "no cue at all"
        raise CueRoleError(
            "No cue in %s's conditioning is ever followed by a Pellet "
            "Delivery within %g s (presented: %s; %d pellets), so neither "
            "pair can be called the food pair." % (
                rat, WINDOW_S, heard, total.get("pellets") or 0))
    if len(fed) > 1:
        raise CueRoleError(
            "More than one cue in %s's conditioning is followed by a Pellet "
            "Delivery within %g s (%s), so which pair gets food is "
            "ambiguous and is not guessed." % (
                rat, WINDOW_S, "; ".join(
                    "%s %d of %d" % (c, total["followed"][c],
                                     total["presented"].get(c, 0))
                    for c in fed)))
    return fed[0]


def roles_for(food_cue, pairings, rat="this rat"):
    """{cue_type: "food" | "no_food"} for the rat's Precon pairings.

    The food pair is the pairing whose SECOND cue is the food cue: in
    sensory preconditioning the first cue is never fed, it is linked to
    food only through the cue it was paired with.
    """
    types = []
    for p in pairings or []:
        ct = p if p in circuit.CUE_TYPES else circuit.cue_type_of(p)
        if ct is None:
            raise CueRoleError("%r is not a cue pairing." % (p,))
        if ct not in types:
            types.append(ct)
    if not types:
        raise CueRoleError("%s has no Precon cue pairings to give roles to."
                           % rat)
    food = [ct for ct in types if circuit.CUE_TYPES[ct][1] == food_cue]
    if not food:
        raise CueRoleError(
            "The food cue in %s's conditioning is %s, but none of its Precon "
            "pairings (%s) ends on %s, so no pair can be called the food "
            "pair." % (rat, food_cue, "; ".join(circuit.cue_label(t)
                                                for t in types), food_cue))
    if len(food) > 1:
        raise CueRoleError(
            "Two of %s's Precon pairings end on the food cue %s (%s), so "
            "which is the food pair is ambiguous." % (
                rat, food_cue, "; ".join(circuit.cue_label(t)
                                         for t in food)))
    return {ct: ("food" if ct == food[0] else "no_food") for ct in types}


# --------------------------------------------------------------------------
# Reading the files
# --------------------------------------------------------------------------
def read_rows(folder):
    """`spark.read_events` on a recording folder, in Spark's time frame."""
    nev = os.path.join(folder, "Events.nev")
    if not os.path.exists(nev):
        return None
    rows, _meta = spark.read_events(nev, nlx.recording_start_us(folder))
    return rows


def read_sessions(recs, reader=None):
    """[(rec, folder, rows)] for every reachable, distinct folder, and
    [{gid, why}] for every record skipped."""
    reader = reader or read_rows
    seen, got, skipped = {}, [], []
    for r in recs:
        folder = here_of(r)
        if not folder:
            skipped.append({"gid": r.get("gid"), "why":
                            "none of its paths is reachable from here"})
            continue
        key = _folder_key(folder)
        if key in seen:
            skipped.append({"gid": r.get("gid"), "why":
                            "the same folder as %s, read once" % seen[key]})
            continue
        seen[key] = r.get("gid")
        rows = reader(folder)
        if rows is None:
            skipped.append({"gid": r.get("gid"), "why": "no Events.nev"})
            continue
        got.append((r, folder, rows))
    return got, skipped


def pairings_of(rat, records, reader=None):
    """The rat's ordered pairings, read off its Precon SPC recordings with
    Spark's own pairing rule. Returns ([cue_type...], [gid...])."""
    recs = records_for(rat, records, PRECON_PHASE)
    got, _skipped = read_sessions(recs, reader)
    types, gids = [], []
    for r, _folder, rows in got:
        pairs, _unpaired = spark.pair_events(rows)
        found = False
        for p in pairs:
            ct = circuit.cue_type_of(p)
            if ct is None:
                continue
            found = True
            if ct not in types:
                types.append(ct)
        if found:
            gids.append(r.get("gid"))
    return types, gids


# --------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------
def role_table(rat, records=None, pairings=None, window_s=WINDOW_S,
               reader=None):
    """The contract shape (arc_contracts.md 7.2)::

        {"rat": 3, "food_cue": "Low Tone",
         "roles": {cue_type: "food" | "no_food"},
         "food_pair": cue_type, "no_food_pairs": [cue_type],
         "source": {"sessions": [gid...], "followed": {cue: n},
                    "presented": {cue: n}, "pellets": n, "window_s": 15.0,
                    "rule": "...", "skipped": [{gid, why}],
                    "per_session": [{gid, label, followed, presented,
                                     pellets}],
                    "pairings_from": [gid...]}}

    `records`: registry records (one `REG.all()`); loaded when None.
    `pairings`: the rat's cue types when the caller already knows them
    (e.g. from the banked pairs); read from its Precon SPC files when None.
    `reader(folder) -> rows`: for tests. Raises CueRoleError.
    """
    n = rat_of(rat)
    name = "r%d" % n
    if records is None:
        records = load_records()
    con = records_for(n, records, CON_PHASE)
    if not con:
        raise CueRoleError("%s has no Con SPC recording in the registry, so "
                           "its food cue cannot be read." % name)
    got, skipped = read_sessions(con, reader)
    per, tallies, used = [], [], []
    for r, _folder, rows in got:
        t = tally(rows, window_s)
        if not t["presented"]:
            # A record called SPC whose file holds no cue at all is a
            # misfiled FP run. Said, never counted as "no food".
            skipped.append({"gid": r.get("gid"), "why":
                            "its Events.nev holds no cue TTL (%d pellets) -- "
                            "not a cued run whatever the registry calls it"
                            % t["pellets"]})
            continue
        tallies.append(t)
        used.append(r.get("gid"))
        per.append({"gid": r.get("gid"), "label": r.get("label"),
                    "con_n": r.get("phase_n"),
                    "presented": t["presented"], "followed": t["followed"],
                    "pellets": t["pellets"]})
    if not tallies:
        raise CueRoleError(
            "None of %s's %d Con SPC recording%s could be read with cues in "
            "it (%s)." % (name, len(con), "" if len(con) == 1 else "s",
                          "; ".join("%s: %s" % (s["gid"], s["why"])
                                    for s in skipped)))
    total = combine(tallies)
    food_cue = food_cue_of(total, name)
    pfrom = []
    if pairings is None:
        pairings, pfrom = pairings_of(n, records, reader)
    roles = roles_for(food_cue, pairings, name)
    food_pair = next(ct for ct, r in roles.items() if r == "food")
    return {
        "rat": n,
        "food_cue": food_cue,
        "no_food_cues": sorted((c for c, k in total["followed"].items()
                                if not k), key=_cue_order),
        "roles": roles,
        "food_pair": food_pair,
        "no_food_pairs": [ct for ct, r in roles.items() if r == "no_food"],
        "source": {
            "sessions": used,
            "followed": {c: total["followed"][c] for c in sorted(
                total["followed"], key=_cue_order)},
            "presented": {c: total["presented"][c] for c in sorted(
                total["presented"], key=_cue_order)},
            "pellets": total["pellets"],
            "unclaimed_pellets": total["unclaimed"],
            "latency_s": {c: total["latency"][c] for c in sorted(
                total["latency"], key=_cue_order)},
            "window_s": float(window_s),
            "rule": RULE,
            "skipped": skipped,
            "per_session": per,
            "pairings_from": pfrom,
        },
    }


def role_source(table):
    """What a circuit carries as `role_source`: enough to see where the role
    came from, small enough to ride in every payload, and deterministic."""
    s = table["source"]
    return {"rat": table["rat"], "food_cue": table["food_cue"],
            "food_pair": table["food_pair"],
            "sessions": list(s["sessions"]),
            "followed": dict(s["followed"]),
            "presented": dict(s["presented"]),
            "window_s": s["window_s"], "rule": s["rule"],
            "read_by": "backend/cueroles.py"}


def role_tables(rats, records=None, reader=None):
    """{rat: table} for several rats, or {rat: {"error": sentence}}."""
    if records is None:
        records = load_records()
    out = {}
    for rat in rats:
        n = rat_of(rat)
        try:
            out[n] = role_table(n, records, reader=reader)
        except CueRoleError as exc:
            out[n] = {"rat": n, "error": str(exc)}
    return out
