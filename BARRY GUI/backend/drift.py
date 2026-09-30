"""
drift.py -- two groups of circuits, each pooled, then the difference.

Step four of The Arc. A circuit (backend/circuit.py) is one recording's
connectivity matrix: for every region pair, in every window, by every
method, the value each usable cue pair gave, with n, mean and SD. Drift takes
a LEFT group and a RIGHT group of those circuits -- say, every Precon
recording against every Postcon recording -- pools each group per cell, and
reports the difference with a p and a Benjamini-Hochberg q.

Pure: no Flask, no files, no clock. Everything arrives as arguments and
leaves as a JSON-safe dict (no NaN, no Infinity -- a number that cannot be
computed is None, with a sentence saying why).

THE UNIT IS THE RECORDING, NOT THE CUE PAIR
-------------------------------------------
A recording's eight cue pairs are not eight independent observations of the
group. They share the animal, the electrode, the day, the impedance, the
histology, the reference -- everything that makes one recording's coupling
sit higher or lower than another's. Pooling every pair of every recording
into one sample and computing an SE from it treats 8 x 5 = 40 correlated
numbers as 40 independent ones: n is overstated, the SE is too small and the
p is too confident, and it gets MORE confident the more pairs each recording
happens to have, even though another pair from the same recording tells you
almost nothing new about the next recording. (tools/check_drift.py shows
this side by side: duplicate every pair and the pair-pooled p collapses
while the nested p barely moves.)

So pairs are nested within recordings. Each recording contributes ONE
estimate -- its mean -- with the uncertainty of that mean (se_r^2 =
sd_r^2 / n_r), and the recordings are combined by inverse-variance
meta-analysis. A recording with many clean pairs has a precise mean and
weighs more; one with a single usable pair weighs less. That is the user's
requirement ("weighing must account for it"), and it is what inverse-
variance weighting does by construction.

WHY RANDOM EFFECTS AND NOT FIXED
--------------------------------
A fixed-effect pool assumes every recording measures the SAME true value and
differs only by within-recording noise. Recordings from different rats,
electrodes and days do not: the true coupling differs from recording to
recording. Fixed-effect weights then let the one or two recordings with the
most pairs dominate, and the SE (sqrt(1 / sum w)) keeps shrinking as pairs
are added -- the same overconfidence as pair-pooling, just one level up.
DerSimonian-Laird estimates the between-recording variance tau^2 from how
much the recording means scatter beyond what their SEs explain, and adds it
to every recording's variance. When recordings genuinely differ, the weights
flatten towards equal and the SE is bounded below by roughly
sqrt(tau^2 / k), however many pairs each recording has. When they agree,
tau^2 is 0 and it reduces to the fixed-effect answer.

DL is a moment estimator and is chosen because it is closed-form, standard,
and can be read and checked by hand. With few recordings per side it is
imprecise, and the z test on its pooled mean is known to be anti-
conservative for small k (see the notes in check_drift.py's report).

ONE RECORDING ON A SIDE (k = 1)
-------------------------------
With one recording there is no scatter between recordings to measure, so
tau^2 cannot be estimated and is taken as 0. The SE of that side is then the
within-recording SE only: it says how well THAT recording's mean is known,
not how well the GROUP's mean is known. Every such cell carries a warning,
because a delta against a k = 1 side is a statement about one recording.

ONE USABLE PAIR IN A RECORDING (n_r = 1)
----------------------------------------
Circuit keeps a region that was usable in even one cue pair (the user's
decision: warn, never drop). One value has no SD, so its se_r is unknown.
Dropping the recording would throw away real data the user chose to keep;
giving it an SE of 0 would give it infinite weight. Instead it borrows the
pooled within-recording SD of that same cell from the other recordings on
the same side,
    sd_pool = sqrt( sum (n_r - 1) sd_r^2 / sum (n_r - 1) ),
the usual pooled estimate of a common within-recording SD. Its se_r^2 is
then sd_pool^2 / 1 -- the largest SE any recording on that side can have for
that spread, so it counts, and counts least. If no recording on that side has
n >= 2 there is nothing to borrow: the side's mean is still reported, the
test is marked impossible, and the cell says why.

WHY BH PER PANEL
----------------
A panel -- one window, one method -- is the 66-cell matrix the user looks at
as one picture, and the question asked of it is "which edges of this network
changed". Benjamini-Hochberg across that panel controls the expected share
of false discoveries among the edges highlighted in that picture. It is not
corrected across windows or methods: those are different questions asked of
the same data (and the three methods are strongly correlated with each
other), and pooling all ~800 cells into one family would make the display
depend on how many other panels happened to be computed. Uncorrected p is
reported alongside q so a reader can apply any other correction.

API (contract section 4, arc_contracts.md)
------------------------------------------
    compatible(left, right, left_refs=None, right_refs=None,
               cue_equivalence=None)     -> (bool, [sentences])
    pool(cells_by_recording)             -> dict   one side, one cell
    z_test(left_pool, right_pool)        -> {se, stat, p}   the swappable test
    build(left_payloads, right_payloads,
          left_refs, right_refs, labels,
          computed_on=None, cue_equivalence=None,
          test=None, progress=None)      -> dict   the arc.drift/1 payload
    summary(payload)                     -> dict   n_summary for the artifact

Parameters are compared only where the kind reads them (pad_s for state,
before_s/after_s for transition), members are pinned and de-duplicated by
version_id, and circuits of different ordered cue pairings are refused unless
a person recorded an equivalence (arc_contracts.md 0a). Two weaknesses are
said on every result rather than hidden: a side with k = 1 (K1_SAY) and the
optimism of the z test with few recordings (Z_NOTE).
"""
import math


SCHEMA = "arc.drift/1"
CIRCUIT_SCHEMA = "arc.circuit/1"
METHOD = "DerSimonian-Laird random effects; BH across each panel"

#: Analysis parameters that change the numbers a circuit holds. Two circuits
#: that differ on any of these are not measurements of the same thing, and a
#: delta between them would mix a methods change into the biology.
NUMBER_PARAMS = ("low", "high", "summary_hz", "max_lag_ms", "notch_hz",
                 "pad_s", "before_s", "after_s", "analysis_fs")

#: Which window lengths a kind actually READS. A state circuit cuts its four
#: windows with `pad_s` and never looks at before/after (Spark writes them as
#: None on a state entry); a transition circuit cuts around the boundaries
#: with before/after and its pad is irrelevant. Comparing a parameter the
#: kind does not use would refuse two identical analyses because one of them
#: carries a stale or None value in a field nothing read.
_COMMON_PARAMS = ("low", "high", "summary_hz", "max_lag_ms", "notch_hz",
                  "analysis_fs")
KIND_PARAMS = {"state": _COMMON_PARAMS + ("pad_s",),
               "transition": _COMMON_PARAMS + ("before_s", "after_s")}


def number_params(kind):
    """The parameters that change the numbers for this kind of circuit.
    An unknown kind compares every one of them (the strict answer)."""
    return KIND_PARAMS.get(kind, NUMBER_PARAMS)


#: Top-level payload fields that must match for the cells to line up at all.
SHAPE_FIELDS = ("kind", "cue_type", "windows", "methods", "region_order")

#: Said on every result, because it is true of every result with few
#: recordings and nothing in the numbers shows it.
Z_NOTE = ("With few recordings per side the z test on a DerSimonian-Laird "
          "pooled mean is optimistic: tau2 is estimated imprecisely and "
          "treated as known, so p and q come out smaller than they should. "
          "Read a q near the threshold with that in mind.")
K1_SAY = "one recording — no between-recording spread can be estimated"


class DriftError(ValueError):
    """Refused. `.reasons` is the list of sentences saying why."""

    def __init__(self, reasons):
        self.reasons = list(reasons)
        super(DriftError, self).__init__(" ".join(self.reasons))


# ---------------------------------------------------------------------------
# Small statistical pieces, each checkable by hand (tools/check_drift.py
# re-derives every one of these with plain loops and compares to 1e-12).
# ---------------------------------------------------------------------------

def _pooled_sd(ns, sds):
    """Pooled within-recording SD over recordings with n >= 2 and an SD.

    sqrt( sum (n-1) sd^2 / sum (n-1) ). None when nobody qualifies.
    """
    num = 0.0
    den = 0
    for n, sd in zip(ns, sds):
        if sd is None or n < 2:
            continue
        num += (n - 1) * sd * sd
        den += n - 1
    if den == 0:
        return None
    return math.sqrt(num / den)


def _dl_tau2(ys, vs):
    """DerSimonian-Laird between-recording variance.

    Fixed-effect weights w = 1/v; Cochran's Q = sum w (y - y_fe)^2;
    C = sum w - sum w^2 / sum w; tau^2 = max(0, (Q - (k-1)) / C).
    k = 1 -> 0 (nothing to scatter). Returns (tau2, Q).
    """
    k = len(ys)
    if k < 2:
        return 0.0, 0.0
    w = [1.0 / v for v in vs]
    sw = sum(w)
    y_fe = sum(wi * yi for wi, yi in zip(w, ys)) / sw
    q = sum(wi * (yi - y_fe) ** 2 for wi, yi in zip(w, ys))
    c = sw - sum(wi * wi for wi in w) / sw
    if c <= 0:
        return 0.0, q
    return max(0.0, (q - (k - 1)) / c), q


def _re_pool(ys, vs, tau2):
    """Random-effects pooled mean and SE given tau^2.

    w_r = 1 / (v_r + tau^2); mean = sum w y / sum w; SE = sqrt(1 / sum w).
    Returns (mean, se, weights).
    """
    w = [1.0 / (v + tau2) for v in vs]
    sw = sum(w)
    mean = sum(wi * yi for wi, yi in zip(w, ys)) / sw
    return mean, math.sqrt(1.0 / sw), w


def _z_p(delta, se):
    """z and two-sided normal p. (None, None) when the SE is unusable."""
    if se is None or not (se > 0) or not math.isfinite(se):
        return None, None
    z = delta / se
    # 2 * norm.sf(|z|) is erfc(|z| / sqrt 2), from the standard library.
    # scipy.stats was imported at load for this one line and cost 831 ms of
    # server start-up; the two agree to 4e-13 relative over z in [0, 40].
    return z, float(math.erfc(abs(z) / math.sqrt(2.0)))


def _bh(pvals):
    """Benjamini-Hochberg q for a list of p (None entries pass through).

    Sort ascending; q_(i) = min over j >= i of p_(j) * m / j, capped at 1.
    m is the number of non-None p -- the tests actually performed.
    """
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    out = [None] * len(pvals)
    if m == 0:
        return out
    order = sorted(idx, key=lambda i: pvals[i])
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvals[i] * m / rank)
        out[i] = min(1.0, running)
    return out


# ---------------------------------------------------------------------------
# One side, one cell.
# ---------------------------------------------------------------------------

def _as_members(cells_by_recording):
    """Accept {member: cell_or_None} or [cell_or_None, ...]."""
    if isinstance(cells_by_recording, dict):
        return list(cells_by_recording.items())
    return [("recording %d" % (i + 1), c)
            for i, c in enumerate(cells_by_recording or [])]


def pool(cells_by_recording):
    """Pool one cell across the recordings of one side.

    `cells_by_recording`: {member name: circuit cell or None} (a list is
    accepted too). A circuit cell is the section-3 shape: {n, mean, sd,
    values, of, warn}. None means that recording has no such cell (a grey
    region, or no pair with both regions usable) and it simply does not take
    part -- it is counted in `missing`, never as a zero.

    Returns {mean, se, tau2, q_het, k, n, testable, why, members, missing,
    warn}. `mean` is None only when k = 0. `se` is None when the test is
    impossible, and `why` says why.
    """
    members = []
    missing = []
    for name, cell in _as_members(cells_by_recording):
        if cell is None or cell.get("mean") is None or not cell.get("n"):
            missing.append(name)
            continue
        members.append((name, cell))

    out = {"mean": None, "se": None, "tau2": None, "q_het": None,
           "k": len(members), "n": sum(int(c["n"]) for _, c in members),
           "testable": False, "why": None, "members": [],
           "missing": missing, "warn": []}
    if not members:
        out["why"] = "no recording on this side has this cell"
        return out

    names = [m for m, _ in members]
    ys = [float(c["mean"]) for _, c in members]
    ns = [int(c["n"]) for _, c in members]
    sds = [None if c.get("sd") is None else float(c["sd"])
           for _, c in members]

    for name, c in members:
        if c.get("warn"):
            out["warn"].append("%s: %s" % (name, c["warn"]))

    sd_pool = _pooled_sd(ns, sds)
    vs = []
    borrowed = []
    for name, n, sd in zip(names, ns, sds):
        if sd is not None and n >= 2:
            vs.append(sd * sd / n)
            borrowed.append(False)
        elif sd_pool is not None:
            # n = 1 (or no SD recorded): borrow the side's pooled
            # within-recording SD rather than drop the recording.
            vs.append(sd_pool * sd_pool / n)
            borrowed.append(True)
            out["warn"].append(
                "%s had %d usable pair%s, so its SD was borrowed from the "
                "other recordings on this side (pooled SD %.4g)"
                % (name, n, "" if n == 1 else "s", sd_pool))
        else:
            vs.append(None)
            borrowed.append(True)

    def _detail(weights=None):
        tot = sum(weights) if weights else None
        return [{"member": nm, "n": n, "mean": y,
                 "sd": sd, "sd_borrowed": b,
                 "weight": None if not weights else weights[i] / tot}
                for i, (nm, n, y, sd, b)
                in enumerate(zip(names, ns, ys, sds, borrowed))]

    if any(v is None for v in vs):
        # Nobody on this side has two usable pairs: no within-recording
        # spread exists anywhere to put an SE on.
        out["mean"] = sum(ys) / len(ys)
        out["members"] = _detail()
        out["why"] = ("no recording on this side has 2 or more usable pairs "
                      "for this cell, so there is no spread to put an SE on; "
                      "the mean is the plain mean of the recordings")
        out["warn"].append("test impossible: " + out["why"])
        return out

    if any(v == 0 for v in vs):
        # SD 0 with n >= 2: every pair gave the identical value. Inverse
        # variance would give that recording infinite weight. Refuse to test
        # rather than invent a floor.
        zero = [nm for nm, v in zip(names, vs) if v == 0]
        out["mean"] = sum(ys) / len(ys)
        out["members"] = _detail()
        out["why"] = ("%s gave the identical value in every pair (SD 0), so "
                      "its precision is infinite and it cannot be weighed"
                      % ", ".join(zero))
        out["warn"].append("test impossible: " + out["why"])
        return out

    tau2, q = _dl_tau2(ys, vs)
    mean, se, w = _re_pool(ys, vs, tau2)
    out.update(mean=mean, se=se, tau2=tau2, q_het=q, testable=True,
               members=_detail(w))
    if len(members) == 1:
        out["warn"].append(
            K1_SAY + " (k = 1), so tau2 = 0 and the SE is that one "
            "recording's within-recording SE -- it describes the recording, "
            "not the group")
    return out


# ---------------------------------------------------------------------------
# The test between the two sides. ONE function, swappable: `build(...,
# test=...)`. It is handed each side's pool (mean, se, tau2, k, members with
# their means and weights) so a Hartung-Knapp or t-based replacement has
# everything it needs without pool() changing.
# ---------------------------------------------------------------------------

def z_test(lp, rp):
    """delta = right - left; SE = sqrt(SE_L^2 + SE_R^2); z; two-sided normal
    p. Returns {se, stat, p}; se/stat/p are None when either side cannot be
    tested."""
    if not (lp.get("testable") and rp.get("testable")):
        return {"se": None, "stat": None, "p": None}
    se = math.sqrt(lp["se"] ** 2 + rp["se"] ** 2)
    z, p = _z_p(rp["mean"] - lp["mean"], se)
    return {"se": se, "stat": z, "p": p}


z_test.label = "z (normal), two-sided"
TESTS = {"z": z_test}


# ---------------------------------------------------------------------------
# Compatibility.
# ---------------------------------------------------------------------------

def _ref_get(ref, *keys):
    for k in keys:
        if ref and ref.get(k) is not None:
            return ref.get(k)
    return None


def _member_name(side, i, payload, ref):
    nm = _ref_get(ref, "nickname", "name")
    if not nm:
        src = (payload or {}).get("source") or {}
        nm = src.get("session_label") or src.get("gid")
    return "%s: %s" % (side, nm or "#%d" % (i + 1))


def _fmt(v):
    if v is None:
        return "not recorded"
    if isinstance(v, float):
        return "%g" % v
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(str(x) for x in v) + "]"
    return str(v)


def _norm(v):
    """Comparable form: numbers as floats, lists as tuples."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list):
        return tuple(_norm(x) for x in v)
    return v


def _disagreement(field, rows):
    """rows: [(side, member name, value)]. A sentence, or None if all agree."""
    groups = {}
    order = []
    for side, name, val in rows:
        key = _norm(val)
        if key not in groups:
            groups[key] = (val, [])
            order.append(key)
        groups[key][1].append((side, name))
    if len(groups) < 2:
        return None
    within = [s for s in ("left", "right")
              if len({_norm(v) for sd, _, v in rows if sd == s}) > 1]
    where = ("within the %s group" % " and within the ".join(within)
             if within else "across the two groups")
    parts = ["%s for %s" % (_fmt(groups[k][0]),
                            ", ".join(n for _, n in groups[k][1]))
             for k in order]
    return "They differ on %s %s: %s." % (field, where, "; ".join(parts))


def cue_classes(cue_equivalence):
    """{cue_type: representative} from [{from, to}, ...] (union-find).

    Only what a person said is joined: a cue type nobody named stays its
    own class, so the default -- no equivalence -- keeps every pairing
    apart (arc_contracts.md 0a: never guess an equivalence)."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for e in cue_equivalence or []:
        a, b = (e or {}).get("from"), (e or {}).get("to")
        if not a or not b or a == b:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return {k: find(k) for k in list(parent)}


def clean_equivalence(cue_equivalence):
    """The equivalence as recorded: each {from, to, by, at}, from/to sorted
    within the pair and the list sorted, duplicates dropped -- so the same
    decision always reads the same. Raises DriftError on a malformed one."""
    out, seen = [], set()
    for e in cue_equivalence or []:
        if not isinstance(e, dict):
            raise DriftError(["A cue equivalence is a {from, to} pair; got %r."
                              % (e,)])
        a, b = e.get("from"), e.get("to")
        if not a or not b or not isinstance(a, str) or not isinstance(b, str):
            raise DriftError(["A cue equivalence has to name two cue types "
                              "(from and to); this one names %r and %r."
                              % (a, b)])
        if a == b:
            continue
        a, b = sorted((a, b))
        if (a, b) in seen:
            continue
        seen.add((a, b))
        out.append({"from": a, "to": b, "by": e.get("by"), "at": e.get("at")})
    out.sort(key=lambda x: (x["from"], x["to"]))
    return out


def _cue_sentence(members, classes):
    """The refusal when the cue types differ, naming both (all) pairings in
    words, and saying what the way through is."""
    by = {}
    order = []
    for sd, n, p, _ in members:
        ct = p.get("cue_type")
        if ct not in by:
            by[ct] = (p.get("cue_label") or ct, [])
            order.append(ct)
        by[ct][1].append(n)
    groups = {}
    for ct in order:
        groups.setdefault(classes.get(ct, ct), []).append(ct)
    if len(groups) < 2:
        return None
    parts = ["%s (%s)" % (by[ct][0], ", ".join(by[ct][1])) for ct in order]
    return ("They differ on cue_type: %s. The cohort is counterbalanced, so "
            "which pairings count as the same cue type is a scientific "
            "decision Jarvis does not make for you. To compare them anyway, "
            "choose to treat them as equivalent; that choice is recorded on "
            "the result." % " and ".join(parts))


def compatible(left, right, left_refs=None, right_refs=None,
               cue_equivalence=None):
    """Can these two groups of circuit payloads be compared?

    Returns (ok, sentences). Refuses an empty side, a payload that is not a
    circuit, any disagreement on kind, cue_type, windows, methods,
    region_order or a number-changing parameter (within a side or across),
    the same artifact version on both sides, and the same artifact version
    or the same recording twice within one side (a recording counted twice
    is two votes for one recording -- exactly what nesting forbids).

    Parameters are compared only where the kind reads them (KIND_PARAMS):
    pad_s for state, before_s/after_s for transition.

    `cue_equivalence` ([{from, to}]) joins cue types a PERSON said count as
    the same; without it any two different ordered pairings are refused,
    with a sentence naming both.

    `left_refs`/`right_refs` (optional, parallel to the payload lists) are
    the pinned refs {artifact_id | id, version, version_id, digest, name};
    they name the members and catch duplicates -- by version_id when the
    ref carries one, because version numbers can clash across machines.
    Without them members are named from the payload's source.
    """
    left = list(left or [])
    right = list(right or [])
    left_refs = list(left_refs or [None] * len(left))
    right_refs = list(right_refs or [None] * len(right))
    reasons = []
    if not left:
        reasons.append("The left group is empty: choose at least one circuit.")
    if not right:
        reasons.append("The right group is empty: choose at least one "
                       "circuit.")
    if len(left_refs) != len(left) or len(right_refs) != len(right):
        reasons.append("Each circuit needs exactly one pinned reference "
                       "(artifact id, version, digest).")
    if reasons:
        return False, reasons

    members = []
    for side, pls, refs in (("left", left, left_refs),
                            ("right", right, right_refs)):
        for i, (p, r) in enumerate(zip(pls, refs)):
            members.append((side, _member_name(side, i, p, r), p or {}, r))

    bad = [n for _, n, p, _ in members if p.get("schema") != CIRCUIT_SCHEMA]
    if bad:
        reasons.append("Not a circuit (schema %s expected): %s."
                       % (CIRCUIT_SCHEMA, ", ".join(bad)))
        return False, reasons

    classes = cue_classes(cue_equivalence)
    for f in SHAPE_FIELDS:
        if f == "cue_type":
            s = _cue_sentence(members, classes)
        else:
            s = _disagreement(f, [(sd, n, p.get(f))
                                  for sd, n, p, _ in members])
        if s:
            reasons.append(s)
    kinds = {p.get("kind") for _, _, p, _ in members}
    fields = number_params(next(iter(kinds))) if len(kinds) == 1 \
        else _COMMON_PARAMS
    for f in fields:
        s = _disagreement(f, [(sd, n, (p.get("params") or {}).get(f))
                              for sd, n, p, _ in members])
        if s:
            reasons.append(s)

    # Duplicates: by version id where the ref has one (numbers clash across
    # machines), else by number.
    seen = {}
    for sd, n, p, r in members:
        aid = _ref_get(r, "artifact_id", "id")
        if aid is None:
            continue
        vid = _ref_get(r, "version_id")
        key = (aid, vid if vid is not None else _ref_get(r, "version"))
        seen.setdefault(key, []).append((sd, n, r))
    for (aid, ver), hits in seen.items():
        sides = {sd for sd, _, _ in hits}
        vnum = _ref_get(hits[0][2], "version")
        what = ("artifact %s, version %s%s" % (
            aid, vnum, (" / %s" % ver) if ver != vnum else ""))
        if len(sides) > 1:
            reasons.append(
                "The same circuit (%s) is on both sides "
                "(%s): a group cannot be compared with itself."
                % (what, ", ".join(n for _, n, _ in hits)))
        elif len(hits) > 1:
            reasons.append(
                "The same circuit (%s) is in the %s "
                "group %d times: it would be counted as %d recordings."
                % (what, hits[0][0], len(hits), len(hits)))
    for side in ("left", "right"):
        gids = {}
        for sd, n, p, _ in members:
            if sd != side:
                continue
            g = ((p.get("source") or {}).get("gid"))
            if g:
                gids.setdefault(g, []).append(n)
        for g, names in gids.items():
            if len(names) > 1:
                reasons.append(
                    "Recording %s is in the %s group more than once (%s): "
                    "recordings are the unit, so each may appear once."
                    % (g, side, ", ".join(names)))
    return (not reasons), reasons


# ---------------------------------------------------------------------------
# The drift payload.
# ---------------------------------------------------------------------------

def _grey_of(payload):
    g = set(payload.get("grey") or [])
    for r in payload.get("regions") or []:
        if r.get("status") == "grey":
            g.add(r.get("region"))
    return g


def _why_grey(payload, region):
    for r in payload.get("regions") or []:
        if r.get("region") == region:
            return r.get("why") or r.get("histology") or "grey"
    return "grey"


def _side_cells(side, payloads, names, window, method, a, b):
    """{member: cell or None} for one cell, plus why each missing one is."""
    key = "%s|%s" % (a, b)
    cells = {}
    why = []
    for p, nm in zip(payloads, names):
        grey = _grey_of(p)
        gone = [r for r in (a, b) if r in grey]
        if gone:
            cells[nm] = None
            why.append("%s: %s grey (%s)"
                       % (nm, " and ".join(gone),
                          "; ".join(_why_grey(p, r) for r in gone)))
            continue
        cell = (((p.get("cells") or {}).get(window) or {})
                .get(method) or {}).get(key)
        cells[nm] = cell
        if cell is None:
            why.append("%s: no cue pair had both regions usable" % nm)
    return cells, why


def _ref_out(p, r, name):
    src = p.get("source") or {}
    return {"artifact_id": _ref_get(r, "artifact_id", "id"),
            "version": _ref_get(r, "version"),
            "version_id": _ref_get(r, "version_id"),
            "digest": _ref_get(r, "digest"),
            "name": name,
            "cue_type": p.get("cue_type"),
            "gid": src.get("gid"),
            "n_pairs": p.get("n_pairs")}


def _side_out(pooled):
    keep = ("mean", "se", "tau2", "q_het", "k", "n", "testable", "why",
            "members", "missing")
    return {k: pooled[k] for k in keep}


def build(left_payloads, right_payloads, left_refs, right_refs, labels,
          computed_on=None, cue_equivalence=None, test=None, progress=None):
    """The arc.drift/1 payload. Raises DriftError when `compatible` refuses.

    `labels`: {"left": "...", "right": "..."} (a 2-tuple is accepted).
    `computed_on`: passed through ({"kind": "local"} when omitted).
    `cue_equivalence`: [{from, to, by, at}] -- cue types a person chose to
        treat as the same; recorded verbatim (cleaned, sorted) on the result.
    `test`: the between-sides test, default `z_test` (see TESTS).
    `progress(done_cells, of_cells)`: called after each panel, if given.
    """
    equiv = clean_equivalence(cue_equivalence)
    ok, reasons = compatible(left_payloads, right_payloads,
                             left_refs, right_refs, equiv)
    if not ok:
        raise DriftError(reasons)
    test = test or z_test
    if isinstance(labels, (list, tuple)):
        labels = {"left": labels[0], "right": labels[1]}
    labels = labels or {}

    L, R = list(left_payloads), list(right_payloads)
    lr, rr = list(left_refs), list(right_refs)
    lnames = [_member_name("left", i, p, r).split(": ", 1)[1]
              for i, (p, r) in enumerate(zip(L, lr))]
    rnames = [_member_name("right", i, p, r).split(": ", 1)[1]
              for i, (p, r) in enumerate(zip(R, rr))]
    first = L[0]
    windows = list(first.get("windows") or [])
    methods = list(first.get("methods") or [])
    order = list(first.get("region_order") or [])

    grey_detail = {}
    for side, pls, nms in (("left", L, lnames), ("right", R, rnames)):
        for p, nm in zip(pls, nms):
            for g in sorted(_grey_of(p)):
                grey_detail.setdefault(g, []).append(
                    {"side": side, "member": nm, "why": _why_grey(p, g)})
    grey = [r for r in order if r in grey_detail]

    cells, absent, panels = {}, {}, {}
    n_pairs_order = len(order) * (len(order) - 1) // 2
    of_cells = n_pairs_order * len(windows) * len(methods)
    done_cells = 0
    for w in windows:
        cells[w], absent[w], panels[w] = {}, {}, {}
        for m in methods:
            panel, gone = {}, {}
            for i, a in enumerate(order):
                for b in order[i + 1:]:
                    key = "%s|%s" % (a, b)
                    lc, lwhy = _side_cells("left", L, lnames, w, m, a, b)
                    rc, rwhy = _side_cells("right", R, rnames, w, m, a, b)
                    lp, rp = pool(lc), pool(rc)
                    if lp["k"] == 0 or rp["k"] == 0:
                        empty = [s for s, pp in (("left", lp), ("right", rp))
                                 if pp["k"] == 0]
                        gone[key] = ("no recording in the %s group has this "
                                     "cell (%s)"
                                     % (" or ".join(empty),
                                        "; ".join(lwhy + rwhy)))
                        continue
                    warn = (["left: " + s for s in lp["warn"]]
                            + ["right: " + s for s in rp["warn"]])
                    if lwhy or rwhy:
                        warn.append("pooled over %d of %d left and %d of %d "
                                    "right recordings (%s)"
                                    % (lp["k"], len(L), rp["k"], len(R),
                                       "; ".join(lwhy + rwhy)))
                    delta = rp["mean"] - lp["mean"]
                    t = test(lp, rp)
                    se, z, p = t["se"], t["stat"], t["p"]
                    panel[key] = {"left": _side_out(lp),
                                  "right": _side_out(rp),
                                  "delta": delta, "se": se, "z": z, "p": p,
                                  "q": None, "testable": p is not None,
                                  "warn": warn}
            keys = list(panel)
            qs = _bh([panel[k]["p"] for k in keys])
            for k, q in zip(keys, qs):
                panel[k]["q"] = q
            cells[w][m] = panel
            absent[w][m] = gone
            panels[w][m] = {"tests": sum(1 for k in keys
                                         if panel[k]["p"] is not None),
                            "cells": len(keys), "absent": len(gone)}
            done_cells += n_pairs_order
            if progress:
                progress(done_cells, of_cells)

    params = {}
    for f in number_params(first.get("kind")) + ("kind", "channel_rule"):
        vals = {_norm((p.get("params") or {}).get(f)) for p in L + R}
        if len(vals) == 1:
            params[f] = (first.get("params") or {}).get(f)

    warn = []
    lg = {(p.get("source") or {}).get("gid") for p in L} - {None}
    rg = {(p.get("source") or {}).get("gid") for p in R} - {None}
    both = sorted(lg & rg)
    if both:
        warn.append("Recording%s %s %s on both sides (different versions): "
                    "the two groups are not independent, and the SE of the "
                    "delta assumes they are."
                    % ("s" if len(both) > 1 else "", ", ".join(both),
                       "are" if len(both) > 1 else "is"))

    for side, pls in (("left", L), ("right", R)):
        if len(pls) == 1:
            warn.append("The %s group is %s: its SE describes that recording, "
                        "not a group of them." % (side, K1_SAY))

    # Which ordered pairings are actually in the comparison, and -- only when
    # a person joined some -- what they said. The label reads as the one
    # cue type when there is one, and names every pairing when there is not.
    types, labels_of = [], {}
    for p in L + R:
        ct = p.get("cue_type")
        if ct not in labels_of:
            types.append(ct)
            labels_of[ct] = p.get("cue_label") or ct
    used = set(types)
    equiv = [e for e in equiv if e["from"] in used and e["to"] in used]
    cue_label = first.get("cue_label")
    if len(types) > 1:
        cue_label = " ≡ ".join(labels_of[t] for t in types)

    def side_types(pls):
        seen = []
        for p in pls:
            if p.get("cue_type") not in seen:
                seen.append(p.get("cue_type"))
        return seen

    return {
        "schema": SCHEMA,
        "kind": first.get("kind"),
        "cue_type": first.get("cue_type"),
        "cue_label": cue_label,
        "cue_types": types,
        "cue_equivalence": equiv,
        "windows": windows,
        "methods": methods,
        "region_order": order,
        "left": {"label": labels.get("left"),
                 "k": len(L), "one_recording": len(L) == 1,
                 "cue_types": side_types(L),
                 "members": [_ref_out(p, r, n)
                             for p, r, n in zip(L, lr, lnames)]},
        "right": {"label": labels.get("right"),
                  "k": len(R), "one_recording": len(R) == 1,
                  "cue_types": side_types(R),
                  "members": [_ref_out(p, r, n)
                              for p, r, n in zip(R, rr, rnames)]},
        "test": {"name": getattr(test, "__name__", "test"),
                 "label": getattr(test, "label", None)},
        "notes": [Z_NOTE],
        "grey": grey,
        "grey_detail": grey_detail,
        "cells": cells,
        "absent": absent,
        "panels": panels,
        "params": params,
        "method": METHOD,
        "warn": warn,
        "computed_on": dict(computed_on or {"kind": "local"}),
    }


def summary(payload):
    """The artifact version's `n_summary`: what a list can show without
    opening the payload -- the two groups' sizes, the tests made and how
    many cells pass q < .05 across every panel."""
    p = payload or {}
    tests = sig = cells = 0
    for byw in (p.get("cells") or {}).values():
        for panel in (byw or {}).values():
            for c in (panel or {}).values():
                cells += 1
                if c.get("p") is not None:
                    tests += 1
                if c.get("q") is not None and c["q"] < 0.05:
                    sig += 1
    return {"left_k": len(((p.get("left") or {}).get("members")) or []),
            "right_k": len(((p.get("right") or {}).get("members")) or []),
            "kind": p.get("kind"), "cue_types": p.get("cue_types"),
            "equivalence": len(p.get("cue_equivalence") or []),
            "cells": cells, "tests": tests, "q_lt_05": sig}
