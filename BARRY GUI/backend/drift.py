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

WITHIN RAT: THE MATCHED DESIGN (arc_contracts.md 7.4)
-----------------------------------------------------
When the two sides are the SAME rats on two days (Precon1 against Precon4),
treating them as two independent groups throws away the pairing: a rat whose
coupling sits high on day 1 sits high on day 4 too, and that between-rat
spread lands in both sides' SEs although it cancels out of every rat's own
change. `design="matched"` pairs the circuits by rat (the ref's `rat`,
which driftrun fills from `subject.mouse`) and pools the CHANGES instead:
per rat r, per cell,
    delta_r = mean_right,r - mean_left,r
    v_r     = se_left,r^2 + se_right,r^2      (se^2 = sd^2 / n; n = 1
              borrows that side's pooled within-recording SD of the cell,
              over the other rats' recordings, exactly as pool() does)
then DerSimonian-Laird over the k rats' (delta_r, v_r). A rat that is on
one side only, or twice on a side, is refused by name. A rat missing the
cell on either day (a grey region, no usable pair) sits that cell out, and
the cell says which rats and why. The two days' within-recording variances
are simply added: the covariance of two different recordings' pair means is
taken as zero -- they are different days, different pairs, different noise.

HARTUNG-KNAPP (`test="hk"`)
---------------------------
The z test on a DL pooled mean treats tau^2 as known and the normal as the
reference; with 8 rats both are optimistic. Hartung-Knapp rescales the
variance by how much the rats' changes actually scatter about the pooled
change and refers the ratio to a t on k - 1 df:
    var_HK = sum w_r (delta_r - delta_hat)^2 / ((k - 1) sum w_r),
    t = delta_hat / sqrt(var_HK),   w_r = 1 / (v_r + tau^2).
It is NOT truncated (metafor's test="knha", not "adhoc"): when the rats'
changes agree more closely than their within-rat SEs predict, the factor
sum w (delta - delta_hat)^2 / (k - 1) is below 1 and the HK SE comes out
SMALLER than DL's -- the t reference is then what keeps it honest. Every
HK result says so (HK_NOTE) and every cell carries the factor. k < 2 is not
testable (no degrees of freedom), with the reason. HK is defined here for
the matched design only: two independent groups would need a Satterthwaite
df or a moderator model this module does not pretend to have.

CONTRASTS
---------
`contrast="baseline"`: each member circuit is first turned into a derived
circuit whose windows are cue1-pre, cue2-pre, post-pre (state) or
onset-pre, switch-pre, offset-pre (transition), PER CUE PAIR: v(w, pair) -
v(pre, pair) over the pairs present in both windows, then n, mean and SD of
those differences. A transition circuit has no pre window of its own, so its
baseline is the pre window of the STATE circuit of the same recording,
pairing and band, handed in (pinned) by the caller and checked here: same
recording, same pairing, same number-changing parameters, and every cue
pair they share opening at the same moment. Rest circuits have no baseline.

`contrast="roles"` (the sanity check): four circuits per rat -- the food
pair and the no-food pair, on both days. Per rat
    D_r = (food_right - food_left) - (nofood_right - nofood_left),
    v_r = the sum of the four side variances,
then DL and the test over rats. If the two pairings changed alike, D is
about 0. The cell's `left`/`right` are then the pooled no-food and food
changes (`cell_sides` says so), so the matrix views still mean something.

COMPARED BY CUE ROLE (arc_contracts.md 7.2)
-------------------------------------------
When every member carries `cue_role` (food / no_food, read from the rat's
own conditioning TTLs by backend/cueroles.py), the counterbalanced pairings
are compared by ROLE instead of by ordered pairing -- a recorded, data-
derived equivalence, not the manual one -- and the payload says
`pooled_by: "cue_role"` and carries each member's `role_source`. Some with a
role and some without is refused.

BH ACROSS THE WHOLE DRIFT (`bh_scope="artifact"`)
-------------------------------------------------
One Benjamini-Hochberg family over every tested cell of every panel. One
drift is one band x one kind x one role x one contrast, so this is "per
band, across windows and methods" -- what the Precon1 -> Precon4 analysis
chose. The default stays per panel (the reasoning above).

DEFAULTS
--------
design="independent", test="z", bh_scope="panel", contrast=None is exactly
the behaviour before any of this existed, and the payload it makes is byte
for byte the same -- no new keys -- so a drift filed before still CONFIRMS
when re-run. Every other choice adds `design`, `bh_scope`, `contrast`,
`pooled_by`, `analysis_say`, `test.id` (and `matched`, `baseline`,
`cell_sides` where they apply); a payload without `design` is the default.

API (contract sections 4 and 7.4, arc_contracts.md)
---------------------------------------------------
    options(design, test, bh_scope, contrast) -> dict  validated, defaulted
    compatible(left, right, left_refs=None, right_refs=None,
               cue_equivalence=None, design=None, contrast=None,
               baselines=None, test=None)      -> (bool, [sentences])
    pool(cells_by_recording)             -> dict   one side, one cell
    pool_rats(rows)                      -> dict   DL over rats' changes
    z_test(left_pool, right_pool, pooled=None)  -> {se, stat, p}
    hk_test(left_pool, right_pool, pooled=None) -> {se, stat, p, df, factor}
                                           the swappable test (TESTS)
    baseline_contrast(payload, state=None) -> the derived circuit payload
    build(left_payloads, right_payloads,
          left_refs, right_refs, labels,
          computed_on=None, cue_equivalence=None,
          test=None, progress=None, design=None, bh_scope=None,
          contrast=None, baselines=None, baseline_refs=None)
                                         -> dict   the arc.drift/1 payload
    say_analysis(options, ...)           -> the choices in words
    summary(payload)                     -> dict   n_summary for the artifact

Parameters are compared only where the kind reads them (pad_s for state,
before_s/after_s for transition), members are pinned and de-duplicated by
version_id, and circuits of different ordered cue pairings are refused unless
a person recorded an equivalence (arc_contracts.md 0a). Two weaknesses are
said on every result rather than hidden: a side with k = 1 (K1_SAY) and the
optimism of the z test with few recordings (Z_NOTE).
"""
import math
import re


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
K1_RAT_SAY = "one rat — no between-rat spread can be estimated"

#: Band-mode fields (arc_contracts.md 7.1). A band circuit's coherence is the
#: MEAN over the band and its raw_cc is on band-passed signals; a circuit made
#: before bands existed has neither field and read coherence at one frequency
#: from the unfiltered signal. The theta band's low/high/max_lag equal the old
#: defaults, so without these the two would pass as the same analysis.
#: Compared like NUMBER_PARAMS; absent on both sides agrees (two old
#: circuits), and they reach the payload's params only when set.
MODE_PARAMS = ("band", "coherence_mode", "raw_cc_filtered")

#: The analysis choices (arc_contracts.md 7.4) and today's behaviour.
DESIGNS = ("independent", "matched")
BH_SCOPES = ("panel", "artifact")
CONTRASTS = (None, "baseline", "roles")
DEFAULTS = {"design": "independent", "test": "z", "bh_scope": "panel",
            "contrast": None}

#: cue - baseline: each derived window and the window it is taken from; the
#: baseline is always the state `pre` window (of the same circuit for state,
#: of the same recording+pairing+band's state circuit for transition).
BASELINE_FROM = "pre"
CONTRAST_WINDOWS = {
    "state": (("cue1-pre", "cue1"), ("cue2-pre", "cue2"),
              ("post-pre", "post")),
    "transition": (("onset-pre", "onset"), ("switch-pre", "switch"),
                   ("offset-pre", "offset")),
}
ROLES = ("food", "no_food")
ROLE_SAY = {"food": "food pair", "no_food": "no-food pair"}

Z_NOTE_RATS = ("With few rats the z test on a DerSimonian-Laird pooled change "
               "is optimistic: tau2 is estimated imprecisely and treated as "
               "known, so p and q come out smaller than they should. "
               "Hartung-Knapp (test = hk) is the remedy.")
HK_NOTE = ("Hartung-Knapp: the SE of the pooled change is rescaled by how much "
           "the rats' changes scatter about it, and the test is a t on k - 1 "
           "df. It is not truncated (as metafor's test = \"knha\"): where the "
           "rats agree more closely than their within-rat SEs predict, the "
           "factor is below 1 and the SE is SMALLER than DerSimonian-Laird's; "
           "each cell carries the factor (hk_factor).")


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


def _t_p(t, df):
    """Two-sided p of Student's t on `df` degrees of freedom.

    scipy.special is imported here, on the first Hartung-Knapp test, and not
    at load: start-up pays nothing for a test nobody asked for (the same
    reason _z_p uses erfc). check_drift.py compares it with the closed-form
    integer-df series of Abramowitz & Stegun 26.7.3/26.7.4, written there.
    """
    from scipy.special import stdtr
    return float(2.0 * stdtr(float(df), -abs(float(t))))


def _natkey(s):
    """r3 before r10."""
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", str(s))]


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


def pool_rats(rows):
    """DerSimonian-Laird over the rats' within-rat changes (one cell).

    `rows`: [{rat, delta, v, n, ...}] -- each rat's change and the variance
    of that change (None when a recording behind it had no SE and nothing
    could be borrowed). Extra keys ride along into `deltas`.

    Returns {mean, se, tau2, q_het, k, n, testable, why, deltas, warn} and a
    private `_fit` ({ys, vs, w}) that the test reads and build drops. `se`
    is DL's sqrt(1 / sum w); the test decides what SE it reports.
    """
    rows = list(rows or [])
    out = {"mean": None, "se": None, "tau2": None, "q_het": None,
           "k": len(rows), "n": sum(int(r.get("n") or 0) for r in rows),
           "testable": False, "why": None, "deltas": [], "warn": []}
    if not rows:
        out["why"] = "no rat has this cell on both sides"
        return out
    ys = [float(r["delta"]) for r in rows]
    vs = [r.get("v") for r in rows]

    def detail(w=None):
        tot = sum(w) if w else None
        got = []
        for i, r in enumerate(rows):
            d = {k: v for k, v in r.items() if k != "v"}
            d["se"] = None if r.get("v") is None else math.sqrt(r["v"])
            d["weight"] = None if not w else w[i] / tot
            got.append(d)
        return got

    if any(v is None for v in vs):
        out["mean"] = sum(ys) / len(ys)
        out["deltas"] = detail()
        out["why"] = ("no recording behind %s has 2 or more usable pairs for "
                      "this cell on one of its sides, so there is no spread "
                      "to put an SE on; the change is the plain mean of the "
                      "rats" % ", ".join(r["rat"] for r in rows
                                         if r.get("v") is None))
        out["warn"].append("test impossible: " + out["why"])
        return out
    if any(v == 0 for v in vs):
        zero = [r["rat"] for r in rows if r.get("v") == 0]
        out["mean"] = sum(ys) / len(ys)
        out["deltas"] = detail()
        out["why"] = ("%s gave the identical value in every pair on both "
                      "sides (SD 0), so its change has infinite precision and "
                      "cannot be weighed" % ", ".join(zero))
        out["warn"].append("test impossible: " + out["why"])
        return out
    tau2, q = _dl_tau2(ys, vs)
    mean, se, w = _re_pool(ys, vs, tau2)
    out.update(mean=mean, se=se, tau2=tau2, q_het=q, testable=True,
               deltas=detail(w))
    out["_fit"] = {"ys": ys, "vs": vs, "w": w}
    return out


# ---------------------------------------------------------------------------
# The test between the two sides. ONE function, swappable: `build(...,
# test=...)`. It is handed each side's pool (mean, se, tau2, k, members with
# their means and weights) so a Hartung-Knapp or t-based replacement has
# everything it needs without pool() changing. In the matched design it is
# also handed `pooled=` -- the rats' pooled change from pool_rats, with the
# fit it came from -- and the test is on that.
# ---------------------------------------------------------------------------

def z_test(lp, rp, pooled=None):
    """delta = right - left; SE = sqrt(SE_L^2 + SE_R^2); z; two-sided normal
    p. Returns {se, stat, p}; se/stat/p are None when either side cannot be
    tested. Matched (`pooled` given): z = pooled change / its DL SE."""
    if pooled is not None:
        if not pooled.get("testable"):
            return {"se": None, "stat": None, "p": None,
                    "why": pooled.get("why")}
        z, p = _z_p(pooled["mean"], pooled["se"])
        return {"se": pooled["se"], "stat": z, "p": p}
    if not (lp.get("testable") and rp.get("testable")):
        return {"se": None, "stat": None, "p": None}
    se = math.sqrt(lp["se"] ** 2 + rp["se"] ** 2)
    z, p = _z_p(rp["mean"] - lp["mean"], se)
    return {"se": se, "stat": z, "p": p}


z_test.label = "z (normal), two-sided"
z_test.id = "z"


def hk_test(lp, rp, pooled=None):
    """Hartung-Knapp on the rats' pooled change (matched design).

    var = sum w (y - y_hat)^2 / ((k - 1) sum w), w the random-effects
    weights; t = y_hat / sqrt(var) on k - 1 df; no truncation (metafor
    test="knha"). Returns {se, stat, p, df, factor, why}; `factor` is
    sum w (y - y_hat)^2 / (k - 1), the multiplier on DL's variance."""
    none = {"se": None, "stat": None, "p": None, "df": None, "factor": None}
    if pooled is None:
        return dict(none, why="Hartung-Knapp is built here for the within-rat "
                    "design; two independent groups use z")
    if not pooled.get("testable"):
        return dict(none, why=pooled.get("why"))
    k = int(pooled["k"])
    if k < 2:
        return dict(none, why="one rat: Hartung-Knapp needs at least two "
                    "rats' changes to measure their spread (k - 1 = 0 "
                    "degrees of freedom)")
    fit = pooled["_fit"]
    ys, w, mu = fit["ys"], fit["w"], pooled["mean"]
    sw = sum(w)
    ss = sum(wi * (yi - mu) ** 2 for wi, yi in zip(w, ys))
    var = ss / ((k - 1) * sw)
    if not (var > 0) or not math.isfinite(var):
        return dict(none, df=k - 1, factor=ss / (k - 1),
                    why="every rat changed by exactly the same amount, so "
                    "the Hartung-Knapp variance is 0 and t is undefined")
    se = math.sqrt(var)
    t = mu / se
    return {"se": se, "stat": t, "p": _t_p(t, k - 1), "df": k - 1,
            "factor": ss / (k - 1), "why": None}


hk_test.label = "Hartung-Knapp t on k - 1 df (no truncation)"
hk_test.id = "hk"
TESTS = {"z": z_test, "hk": hk_test}


def _test_of(test):
    """(function, id) from None, an id in TESTS, or a function."""
    if test is None or test == "":
        return z_test, "z"
    if callable(test):
        return test, getattr(test, "id", None)
    if test in TESTS:
        return TESTS[test], test
    raise DriftError(["The test is %r; it is one of %s."
                      % (test, ", ".join(sorted(TESTS)))])


def options(design=None, test=None, bh_scope=None, contrast=None):
    """The analysis choices, validated, with today's defaults filled in.

    Raises DriftError naming every value it does not know. Which choices go
    TOGETHER (Hartung-Knapp and the roles contrast need the matched design)
    is `compatible`'s business, so the pre-flight can say it in words."""
    reasons = []
    d = DEFAULTS["design"] if design in (None, "") else design
    if d not in DESIGNS:
        reasons.append("The design is %r; it is independent (two groups) or "
                       "matched (within rat)." % (d,))
    if callable(test):
        t = getattr(test, "id", None) or getattr(test, "__name__", "test")
    else:
        t = DEFAULTS["test"] if test in (None, "") else test
        if t not in TESTS:
            reasons.append("The test is %r; it is z or hk (Hartung-Knapp)."
                           % (t,))
    b = DEFAULTS["bh_scope"] if bh_scope in (None, "") else bh_scope
    if b not in BH_SCOPES:
        reasons.append("bh_scope is %r; it is panel (BH across each window x "
                       "method) or artifact (across the whole drift)." % (b,))
    c = None if contrast in (None, "", "none") else contrast
    if c not in CONTRASTS:
        reasons.append("The contrast is %r; it is none, baseline (cue minus "
                       "baseline) or roles (food minus no-food change)."
                       % (c,))
    if reasons:
        raise DriftError(reasons)
    return {"design": d, "test": t, "bh_scope": b, "contrast": c}


def is_default(opts):
    """True when these choices are exactly today's behaviour."""
    o = opts or {}
    return all(o.get(k) == v for k, v in DEFAULTS.items())


def say_analysis(opts, rats=None, dfs=None, role=None, bh_tests=None):
    """The choices in words, as the result shows them: "within-rat, 8 rats;
    Hartung-Knapp t on 7 df; BH across all windows and methods".

    `rats`: how many rats the matched design paired; `dfs`: the degrees of
    freedom of the tested cells (a set -- a cell a rat sits out has fewer);
    `role`: the cue role pooled, when pooled by role."""
    o = dict(DEFAULTS, **(opts or {}))
    bits = []
    if o["design"] == "matched":
        bits.append("within-rat" + ("" if rats is None else ", %d rat%s"
                                    % (rats, "" if rats == 1 else "s"))
                    + (", four circuits each" if o["contrast"] == "roles"
                       else ""))
    else:
        bits.append("two independent groups, recordings as the unit")
    if o["test"] == "hk":
        ds = sorted(set(d for d in (dfs or []) if d is not None))
        if not ds:
            bits.append("Hartung–Knapp t on k − 1 df")
        elif len(ds) == 1:
            bits.append("Hartung–Knapp t on %d df" % ds[0])
        else:
            bits.append("Hartung–Knapp t on %d–%d df (fewer where a rat "
                        "lacks the cell)" % (ds[0], ds[-1]))
    elif o["test"] == "z":
        bits.append("z test")
    else:
        bits.append("test: %s" % o["test"])
    bits.append("BH across all windows and methods"
                + ("" if bh_tests is None else " (%d tests)" % bh_tests)
                if o["bh_scope"] == "artifact" else "BH across each panel")
    if o["contrast"] == "baseline":
        bits.append("each window minus the baseline (pre), per cue pair")
    elif o["contrast"] == "roles":
        bits.append("food-pair change minus no-food-pair change, per rat")
    if role:
        bits.append("the %s of each rat" % ROLE_SAY.get(role, role))
    return "; ".join(bits)


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


def _rat_of(ref):
    """The rat a member is from: the ref's `rat`, else `r<mouse>`."""
    if not ref:
        return None
    if ref.get("rat") not in (None, ""):
        return str(ref["rat"])
    if ref.get("mouse") not in (None, ""):
        return "r%s" % ref["mouse"]
    return None


def _role_problems(members):
    """(by_role, sentences). Every member with a cue_role -> compared by role;
    none -> by cue type, as before; some -> refused, naming both sets."""
    has = [n for _, n, p, _ in members if p.get("cue_role") not in (None, "")]
    if not has:
        return False, []
    if len(has) == len(members):
        bad = sorted({str(p.get("cue_role")) for _, _, p, _ in members
                      if p.get("cue_role") not in ROLES})
        if bad:
            return True, ["A cue role is food or no_food; these circuits say "
                          "%s." % ", ".join(bad)]
        return True, []
    without = [n for _, n, p, _ in members
               if p.get("cue_role") in (None, "")]
    return False, [
        "Some circuits carry a cue role (food or no-food pair) and some do "
        "not, so they cannot be matched by role or by pairing: %s %s one; "
        "%s %s not. Re-make the circuits without a role with their role, or "
        "choose circuits that all have one." % (
            ", ".join(has), "has" if len(has) == 1 else "have",
            ", ".join(without), "does" if len(without) == 1 else "do")]


def _baseline_problems(members, baselines):
    """The cue - baseline contrast: every member has a baseline to subtract,
    and a transition member's baseline really is the state circuit of the
    same recording, pairing and band. Sentences, or []."""
    reasons = []
    rest = [n for _, n, p, _ in members if p.get("kind") == "rest"]
    if rest:
        reasons.append("Rest circuits have no baseline window, so there is no "
                       "cue − baseline contrast for them: %s."
                       % ", ".join(rest))
    idx = {"left": 0, "right": 0}
    bases = []
    for side, name, p, _ in members:
        i = idx[side]
        idx[side] += 1
        kind = p.get("kind")
        if kind == "state":
            if BASELINE_FROM not in (p.get("windows") or []):
                reasons.append("%s has no %s window to subtract."
                               % (name, BASELINE_FROM))
            continue
        if kind != "transition":
            continue
        got = ((baselines or {}).get(side) or [])
        b = got[i] if i < len(got) else None
        if not b:
            reasons.append(
                "%s is a transition circuit; cue − baseline takes its "
                "baseline from the %s window of the STATE circuit of the same "
                "recording, pairing and band, and none was given. Make that "
                "state circuit in Circuit first." % (name, BASELINE_FROM))
            continue
        bases.append((side, name, b))
        why = []
        if b.get("schema") != CIRCUIT_SCHEMA or b.get("kind") != "state":
            why.append("it is not a state circuit")
        bs, ps = b.get("source") or {}, p.get("source") or {}
        if bs.get("gid") != ps.get("gid"):
            why.append("it is recording %s, not %s" % (bs.get("gid"),
                                                       ps.get("gid")))
        if b.get("cue_type") != p.get("cue_type"):
            why.append("it is %s, not %s" % (b.get("cue_label")
                                             or b.get("cue_type"),
                                             p.get("cue_label")
                                             or p.get("cue_type")))
        if (b.get("cue_role") or None) != (p.get("cue_role") or None):
            why.append("its cue role is %s, not %s" % (b.get("cue_role"),
                                                       p.get("cue_role")))
        for f in _COMMON_PARAMS + MODE_PARAMS:
            bv = _norm((b.get("params") or {}).get(f))
            pv = _norm((p.get("params") or {}).get(f))
            if bv != pv:
                why.append("%s is %s there and %s here"
                           % (f, _fmt((b.get("params") or {}).get(f)),
                              _fmt((p.get("params") or {}).get(f))))
        for f in ("methods", "region_order"):
            if _norm(b.get(f)) != _norm(p.get(f)):
                why.append("its %s differ" % f)
        if BASELINE_FROM not in (b.get("windows") or []):
            why.append("it has no %s window" % BASELINE_FROM)
        bt = {x.get("pair_id"): x.get("opener_t") for x in b.get("pairs") or []}
        moved = []
        for x in p.get("pairs") or []:
            pid, t = x.get("pair_id"), x.get("opener_t")
            if pid in bt and t is not None and bt[pid] is not None \
                    and abs(float(t) - float(bt[pid])) > 1e-3:
                moved.append("pair %s opens at %.3f s there and %.3f s here"
                             % (pid, float(bt[pid]), float(t)))
        if moved:
            why.append("they are not the same cue pairs (%s)"
                       % "; ".join(moved[:3]))
        if why:
            reasons.append("The baseline given for %s cannot be its baseline: "
                           "%s." % (name, "; ".join(why)))
    if len(bases) > 1:
        s = _disagreement("the baselines' pad_s",
                          [(sd, n, (b.get("params") or {}).get("pad_s"))
                           for sd, n, b in bases])
        if s:
            reasons.append(s)
    return reasons


def _matched_problems(members, contrast, by_role):
    """The within-rat design: every member names its rat, every rat is on
    both sides exactly once (roles: food and no-food pair, both sides), and
    within a rat the same role is the same pairing on both days."""
    reasons = []
    rats, norat = {}, []
    for side, name, p, r in members:
        rat = _rat_of(r)
        if rat is None:
            norat.append(name)
            continue
        role = p.get("cue_role") if contrast == "roles" else None
        rats.setdefault(rat, {}).setdefault((side, role), []).append((name, p))
    if norat:
        reasons.append("The within-rat design pairs circuits by rat, and %s "
                       "%s not say which rat %s from."
                       % (", ".join(norat),
                          "does" if len(norat) == 1 else "do",
                          "it is" if len(norat) == 1 else "they are"))
    for rat in sorted(rats, key=_natkey):
        slots = rats[rat]
        for (side, role), got in sorted(slots.items(),
                                        key=lambda kv: (kv[0][0],
                                                        str(kv[0][1]))):
            if len(got) > 1:
                reasons.append(
                    "Rat %s is in the %s group %d times%s (%s): within rat, "
                    "each rat has one circuit per side%s."
                    % (rat, side, len(got),
                       " as the %s" % ROLE_SAY.get(role, role) if role else "",
                       ", ".join(n for n, _ in got),
                       " and role" if contrast == "roles" else ""))
        if contrast == "roles":
            need = [(s, ro) for s in ("left", "right") for ro in ROLES]
            miss = [k for k in need if k not in slots]
            if miss:
                reasons.append(
                    "Rat %s is missing its %s: the food − no-food contrast "
                    "needs four circuits per rat (the food and the no-food "
                    "pair, on both sides)." % (rat, ", ".join(
                        "%s on the %s" % (ROLE_SAY[ro], s) for s, ro in miss)))
            pairs = [(ro,) for ro in ROLES]
        else:
            sides = {s for s, _ in slots}
            if sides != {"left", "right"}:
                only = sorted(sides)[0] if sides else "no"
                reasons.append(
                    "Rat %s is only in the %s group (%s): the within-rat "
                    "design compares every rat with itself, so each rat needs "
                    "a circuit on both sides." % (
                        rat, only, ", ".join(n for got in slots.values()
                                             for n, _ in got)))
            pairs = [(None,)]
        if by_role:
            for (ro,) in pairs:
                a = slots.get(("left", ro)) or []
                b = slots.get(("right", ro)) or []
                if a and b and a[0][1].get("cue_type") != \
                        b[0][1].get("cue_type"):
                    reasons.append(
                        "Rat %s's %s is %s on the left and %s on the right: "
                        "within a rat a role is one pairing, so these are not "
                        "the same cue pair on two days." % (
                            rat, ROLE_SAY.get(a[0][1].get("cue_role"),
                                              "cue pair"),
                            a[0][1].get("cue_label") or a[0][1].get(
                                "cue_type"),
                            b[0][1].get("cue_label") or b[0][1].get(
                                "cue_type")))
    return reasons


def compatible(left, right, left_refs=None, right_refs=None,
               cue_equivalence=None, design=None, contrast=None,
               baselines=None, test=None):
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

    The analysis choices (arc_contracts.md 7.4; all default to today's):
    `design="matched"` refuses a member with no rat, a rat on one side only
    and a rat twice on a side (each named); `contrast="roles"` needs four
    circuits per rat (food and no-food pair, both sides); `test="hk"` and
    the roles contrast need the matched design; `contrast="baseline"` needs
    a baseline for every member -- a state circuit's own `pre`, or for a
    transition circuit `baselines={"left": [state payload | None, ...],
    "right": [...]}` (parallel to the members) holding the state circuit of
    the same recording, pairing and band. When every member carries a
    `cue_role`, roles are compared instead of pairings; some with and some
    without is refused.
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

    design = design or DEFAULTS["design"]
    test_id = (getattr(test, "id", None) if callable(test)
               else (test or DEFAULTS["test"]))
    by_role, role_why = _role_problems(members)
    reasons.extend(role_why)
    if contrast == "roles" and not by_role and not role_why:
        reasons.append("The food − no-food contrast compares each rat's food "
                       "pair with its no-food pair, so every circuit needs its "
                       "cue role, and these carry none.")

    classes = cue_classes(cue_equivalence)
    for f in SHAPE_FIELDS:
        if f == "cue_type":
            if by_role:
                # Compared by role (7.2): the pairings are counterbalanced
                # across rats, the role is what is the same.
                s = None if contrast == "roles" else _disagreement(
                    "cue_role", [(sd, n, p.get("cue_role"))
                                 for sd, n, p, _ in members])
            else:
                s = _cue_sentence(members, classes)
        else:
            s = _disagreement(f, [(sd, n, p.get(f))
                                  for sd, n, p, _ in members])
        if s:
            reasons.append(s)
    kinds = {p.get("kind") for _, _, p, _ in members}
    fields = number_params(next(iter(kinds))) if len(kinds) == 1 \
        else _COMMON_PARAMS
    for f in fields + MODE_PARAMS:
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
                # The roles contrast puts a recording's food AND no-food
                # circuit on the same side: the unit there is (recording,
                # role), and each of those may appear once.
                if contrast == "roles":
                    g = (g, p.get("cue_role"))
                gids.setdefault(g, []).append(n)
        for g, names in gids.items():
            if len(names) > 1:
                reasons.append(
                    "Recording %s is in the %s group more than once (%s): "
                    "recordings are the unit, so each may appear once."
                    % (g if not isinstance(g, tuple)
                       else "%s (%s)" % (g[0], ROLE_SAY.get(g[1], g[1])),
                       side, ", ".join(names)))

    if test_id == "hk" and design != "matched":
        reasons.append("Hartung-Knapp is used here for the within-rat "
                       "(matched) design, on the rats' changes. Two "
                       "independent groups are tested with z; choose the "
                       "matched design to use it.")
    if contrast == "roles" and design != "matched":
        reasons.append("The food − no-food contrast is a difference of "
                       "changes WITHIN each rat, so it needs the matched "
                       "design.")
    if design == "matched":
        reasons.extend(_matched_problems(members, contrast, by_role))
    if contrast == "baseline":
        reasons.extend(_baseline_problems(members, baselines))
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


# ---------------------------------------------------------------------------
# cue - baseline: a derived circuit, per cue pair.
# ---------------------------------------------------------------------------

def _sd_of(xs):
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def baseline_contrast(payload, state=None):
    """The member circuit with each window replaced by (window - pre), PER
    CUE PAIR, over the pairs present in both; n, mean, SD (ddof 1, None
    under 2), `of` and `warn` recomputed exactly as circuit.build states
    them. A cell no pair survives is absent (not zero).

    State: the circuit's own `pre`. Transition: `state` is the state circuit
    of the same recording, pairing and band (compatible() checks it), and a
    region grey in either is grey in the result. Raises DriftError for a
    kind with no baseline."""
    kind = payload.get("kind")
    if kind not in CONTRAST_WINDOWS:
        raise DriftError(["A %s circuit has no baseline window, so there is no "
                          "cue − baseline contrast for it." % kind])
    base = payload if kind == "state" else state
    if base is None:
        raise DriftError(["A transition circuit's baseline is its state "
                          "circuit's pre window, and none was given."])
    out = dict(payload)
    wins = [(d, w) for d, w in CONTRAST_WINDOWS[kind]
            if w in (payload.get("windows") or [])]
    grey = set(_grey_of(payload)) | set(_grey_of(base))
    regions = []
    for r in payload.get("regions") or []:
        r = dict(r)
        if r.get("region") in grey and r.get("status") != "grey":
            r["status"] = "grey"
            r["why"] = "grey in the baseline circuit: " + _why_grey(
                base, r.get("region"))
        regions.append(r)
    cells = {}
    for dname, w in wins:
        cells[dname] = {}
        for m in payload.get("methods") or []:
            panel = {}
            bpanel = (((base.get("cells") or {}).get(BASELINE_FROM) or {})
                      .get(m) or {})
            for key, c in ((((payload.get("cells") or {}).get(w) or {})
                            .get(m) or {}).items()):
                a, b = key.split("|", 1)
                if a in grey or b in grey:
                    continue
                bc = bpanel.get(key)
                if not bc:
                    continue
                pre = {x.get("pair_id"): x.get("v")
                       for x in bc.get("values") or [] if x.get("v") is not None}
                vals = [{"pair_id": x.get("pair_id"),
                         "v": float(x["v"]) - float(pre[x.get("pair_id")])}
                        for x in c.get("values") or []
                        if x.get("v") is not None and x.get("pair_id") in pre]
                if not vals:
                    continue
                xs = [v["v"] for v in vals]
                n = len(xs)
                of = c.get("of")
                panel[key] = {
                    "n": n, "mean": sum(xs) / n, "sd": _sd_of(xs),
                    "values": vals, "of": of,
                    "warn": ("usable in %d of %d pairs" % (n, of)
                             if of and n < of / 2.0 else None)}
            cells[dname][m] = panel
    out.update(windows=[d for d, _ in wins], cells=cells,
               grey=sorted(grey), regions=regions,
               region_usable={})
    out["contrast_of"] = {"windows": [w for _, w in wins],
                          "baseline": BASELINE_FROM,
                          "baseline_gid": (base.get("source") or {})
                          .get("gid")}
    return out


# ---------------------------------------------------------------------------
# Within rat.
# ---------------------------------------------------------------------------

def _cell_of(p, window, method, a, b):
    """(cell, None) or (None, why) -- one member, one cell."""
    grey = _grey_of(p)
    gone = [r for r in (a, b) if r in grey]
    if gone:
        return None, "%s grey (%s)" % (" and ".join(gone), "; ".join(
            _why_grey(p, r) for r in gone))
    cell = (((p.get("cells") or {}).get(window) or {}).get(method) or {}) \
        .get("%s|%s" % (a, b))
    if cell is None or cell.get("mean") is None or not cell.get("n"):
        return None, "no cue pair had both regions usable"
    return cell, None


def _rats(L, R, lrefs, rrefs, lnames, rnames, roles):
    """[(rat, {(side, role|None): (payload, member name)})] in rat order."""
    by = {}
    for side, pls, refs, names in (("left", L, lrefs, lnames),
                                   ("right", R, rrefs, rnames)):
        for p, r, nm in zip(pls, refs, names):
            role = p.get("cue_role") if roles else None
            by.setdefault(_rat_of(r), {})[(side, role)] = (p, nm)
    return [(rat, by[rat]) for rat in sorted(by, key=_natkey)]


def _gname(g, labels):
    side, role = g
    lab = (labels or {}).get(side) or side
    return lab + (" " + ROLE_SAY.get(role, role) if role else "")


def _rats_side(mp, dropped):
    """pool_rats output in the shape of a side pool (roles contrast)."""
    return {"mean": mp["mean"], "se": mp["se"], "tau2": mp["tau2"],
            "q_het": mp["q_het"], "k": mp["k"], "n": mp["n"],
            "testable": mp["testable"], "why": mp["why"],
            "members": [{"member": d["rat"], "n": d.get("n"),
                         "mean": d["delta"], "sd": None, "se": d.get("se"),
                         "sd_borrowed": False, "weight": d.get("weight")}
                        for d in mp["deltas"]],
            "missing": [d["rat"] for d in dropped]}


def _matched_cell(rats, w, m, a, b, test, test_id, labels, roles):
    """One cell, within rat. Returns (cell, None) or (None, why absent)."""
    groups = ([(s, ro) for ro in ROLES for s in ("left", "right")] if roles
              else [("left", None), ("right", None)])
    complete, dropped = [], []
    for rat, slots in rats:
        got, why = {}, []
        for g in groups:
            p, nm = slots[g]
            c, gone = _cell_of(p, w, m, a, b)
            if c is None:
                why.append("%s: %s" % (_gname(g, labels), gone))
            else:
                got[g] = (c, nm)
        if why:
            dropped.append({"rat": rat, "why": "; ".join(why)})
        else:
            complete.append((rat, got))
    if not complete:
        return None, ("no rat has this cell on both sides (%s)"
                      % "; ".join("%s: %s" % (d["rat"], d["why"])
                                  for d in dropped))

    # The pooled within-recording SD of each side (and role), over the
    # recordings of the rats that take part -- what an n = 1 recording
    # borrows, exactly as pool() does for a side.
    sdp = {}
    for g in groups:
        cs = [got[g][0] for _, got in complete]
        sdp[g] = _pooled_sd([int(c["n"]) for c in cs],
                            [None if c.get("sd") is None else float(c["sd"])
                             for c in cs])
    warn = []

    def var_of(rat, g, c):
        n = int(c["n"])
        sd = c.get("sd")
        if sd is not None and n >= 2:
            return float(sd) ** 2 / n
        if sdp[g] is not None:
            warn.append("%s %s had %d usable pair%s, so its SD was borrowed "
                        "from the other rats' recordings there (pooled SD "
                        "%.4g)" % (rat, _gname(g, labels), n,
                                   "" if n == 1 else "s", sdp[g]))
            return sdp[g] ** 2 / n
        return None

    rows, sub = [], {ro: [] for ro in ROLES}
    for rat, got in complete:
        for g in groups:
            c = got[g][0]
            if c.get("warn"):
                warn.append("%s %s: %s" % (rat, _gname(g, labels), c["warn"]))
        parts = {}
        for ro in (ROLES if roles else (None,)):
            cl, cr = got[("left", ro)][0], got[("right", ro)][0]
            vl = var_of(rat, ("left", ro), cl)
            vr = var_of(rat, ("right", ro), cr)
            parts[ro] = {"delta": float(cr["mean"]) - float(cl["mean"]),
                         "v": None if vl is None or vr is None else vl + vr,
                         "n": int(cl["n"]) + int(cr["n"]),
                         "left": float(cl["mean"]), "right": float(cr["mean"])}
        if roles:
            f, o = parts["food"], parts["no_food"]
            for ro in ROLES:
                sub[ro].append(dict(parts[ro], rat=rat))
            rows.append({"rat": rat, "delta": f["delta"] - o["delta"],
                         "v": (None if f["v"] is None or o["v"] is None
                               else f["v"] + o["v"]),
                         "n": f["n"] + o["n"],
                         "food": f["delta"], "no_food": o["delta"]})
        else:
            x = parts[None]
            rows.append({"rat": rat, "delta": x["delta"], "v": x["v"],
                         "n": x["n"], "left": x["left"], "right": x["right"]})

    mp = pool_rats(rows)
    if roles:
        lp = _rats_side(pool_rats(sub["no_food"]), dropped)
        rp = _rats_side(pool_rats(sub["food"]), dropped)
    else:
        lp = _side_out(pool({got[("left", None)][1]: got[("left", None)][0]
                             for _, got in complete}))
        rp = _side_out(pool({got[("right", None)][1]: got[("right", None)][0]
                             for _, got in complete}))
    t = test(lp, rp, pooled=mp)
    if dropped:
        warn.append("pooled over %d of %d rats (%s)"
                    % (len(complete), len(rats),
                       "; ".join("%s left out: %s" % (d["rat"], d["why"])
                                 for d in dropped)))
    warn.extend(mp["warn"])
    if mp["k"] == 1 and mp["testable"]:
        warn.append(K1_RAT_SAY + " (k = 1), so tau2 = 0 and the SE is that "
                    "one rat's within-rat SE -- it describes the rat, not the "
                    "cohort")
    why = t.get("why")
    if t.get("p") is None and why and mp["testable"]:
        warn.append("test impossible: " + why)
    cell = {"left": lp, "right": rp,
            "delta": mp["mean"], "se": t.get("se"),
            "z": None if test_id == "hk" else t.get("stat"),
            "p": t.get("p"), "q": None, "testable": t.get("p") is not None,
            "warn": warn, "why": why,
            "k": mp["k"], "n": mp["n"], "tau2": mp["tau2"],
            "q_het": mp["q_het"], "se_dl": mp["se"],
            "deltas": mp["deltas"], "dropped": dropped}
    if test_id == "hk":
        cell["t"] = t.get("stat")
        cell["df"] = t.get("df")
        cell["hk_factor"] = t.get("factor")
    return cell, None


def build(left_payloads, right_payloads, left_refs, right_refs, labels,
          computed_on=None, cue_equivalence=None, test=None, progress=None,
          design=None, bh_scope=None, contrast=None, baselines=None,
          baseline_refs=None):
    """The arc.drift/1 payload. Raises DriftError when `compatible` refuses.

    `labels`: {"left": "...", "right": "..."} (a 2-tuple is accepted).
    `computed_on`: passed through ({"kind": "local"} when omitted).
    `cue_equivalence`: [{from, to, by, at}] -- cue types a person chose to
        treat as the same; recorded verbatim (cleaned, sorted) on the result.
    `test`: the between-sides test: "z" (default) or "hk", or a function
        (see TESTS; in the matched design it is called with `pooled=`).
    `progress(done_cells, of_cells)`: called after each panel, if given.
    `design`, `bh_scope`, `contrast`: arc_contracts.md 7.4 (module
        docstring); None is today's behaviour.
    `baselines`, `baseline_refs`: for contrast="baseline", {"left": [...],
        "right": [...]} parallel to the members -- the state circuit payload
        (and its pinned ref) each TRANSITION member takes its pre from; None
        for a state member, which uses its own.
    """
    equiv = clean_equivalence(cue_equivalence)
    test_fn, test_id = _test_of(test)
    opts = options(design, test_id if test_id else test_fn, bh_scope,
                   contrast)
    design, bh_scope, contrast = (opts["design"], opts["bh_scope"],
                                  opts["contrast"])
    ok, reasons = compatible(left_payloads, right_payloads,
                             left_refs, right_refs, equiv, design=design,
                             contrast=contrast, baselines=baselines,
                             test=test_id)
    if not ok:
        raise DriftError(reasons)
    test = test_fn
    if isinstance(labels, (list, tuple)):
        labels = {"left": labels[0], "right": labels[1]}
    labels = labels or {}

    L0, R0 = list(left_payloads), list(right_payloads)
    lr, rr = list(left_refs), list(right_refs)
    lnames = [_member_name("left", i, p, r).split(": ", 1)[1]
              for i, (p, r) in enumerate(zip(L0, lr))]
    rnames = [_member_name("right", i, p, r).split(": ", 1)[1]
              for i, (p, r) in enumerate(zip(R0, rr))]
    by_role = all(p.get("cue_role") not in (None, "") for p in L0 + R0)
    matched = design == "matched"
    roles = contrast == "roles"
    # Anything but today's behaviour says what it was on the payload; today's
    # adds no key, so a drift filed before re-runs to the same digest. (A
    # function passed as `test` is recorded by name, as it always was.)
    extended = (matched or bh_scope != "panel" or contrast is not None
                or test_id == "hk" or by_role)
    if contrast == "baseline":
        bl = (baselines or {}).get("left") or [None] * len(L0)
        br = (baselines or {}).get("right") or [None] * len(R0)
        L = [baseline_contrast(p, b) for p, b in zip(L0, bl)]
        R = [baseline_contrast(p, b) for p, b in zip(R0, br)]
    else:
        L, R = L0, R0
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
    rats = _rats(L, R, lr, rr, lnames, rnames, roles) if matched else None
    for w in windows:
        cells[w], absent[w], panels[w] = {}, {}, {}
        for m in methods:
            panel, gone = {}, {}
            for i, a in enumerate(order):
                for b in order[i + 1:]:
                    key = "%s|%s" % (a, b)
                    if matched:
                        c, why = _matched_cell(rats, w, m, a, b, test,
                                               test_id, labels, roles)
                        if c is None:
                            gone[key] = why
                        else:
                            panel[key] = c
                        continue
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
            if bh_scope == "panel":
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

    # One BH family over every tested cell of every panel: the drift is one
    # band x kind x role x contrast, so this is per band, across windows and
    # methods (7.4).
    bh_tests = None
    if bh_scope == "artifact":
        every = [(w, m, k) for w in windows for m in methods
                 for k in cells[w][m]]
        qs = _bh([cells[w][m][k]["p"] for w, m, k in every])
        for (w, m, k), q in zip(every, qs):
            cells[w][m][k]["q"] = q
        bh_tests = sum(1 for w, m, k in every
                       if cells[w][m][k]["p"] is not None)

    params = {}
    for f in number_params(first.get("kind")) + ("kind", "channel_rule"):
        vals = {_norm((p.get("params") or {}).get(f)) for p in L + R}
        if len(vals) == 1:
            params[f] = (first.get("params") or {}).get(f)
    for f in MODE_PARAMS:
        vals = {_norm((p.get("params") or {}).get(f)) for p in L + R}
        if len(vals) == 1 and (first.get("params") or {}).get(f) is not None:
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

    out = {
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
    if not extended:
        return out
    return _extend(out, opts, test, test_id, L0, R0, lr, rr, lnames, rnames,
                   rats, by_role, bh_tests, baselines, baseline_refs, labels)


def _extend(out, opts, test, test_id, L0, R0, lr, rr, lnames, rnames, rats,
            by_role, bh_tests, baselines, baseline_refs, labels):
    """What a non-default drift adds to the payload (7.4): the choices, in
    fields and in words, the rats and their pairs, the baselines read."""
    design, bh_scope, contrast = (opts["design"], opts["bh_scope"],
                                  opts["contrast"])
    matched = design == "matched"
    out["design"] = design
    out["bh_scope"] = bh_scope
    out["contrast"] = contrast
    out["pooled_by"] = "cue_role" if by_role else "cue_type"
    out["test"]["id"] = test_id
    role = None
    if by_role:
        roles_here = sorted({p.get("cue_role") for p in L0 + R0})
        out["cue_roles"] = roles_here
        role = roles_here[0] if len(roles_here) == 1 else None
        out["cue_role"] = role
        out["cue_label"] = (ROLE_SAY.get(role, role) if role else
                            "food pair − no-food pair")
        for side, pls in (("left", L0), ("right", R0)):
            for mem, p in zip(out[side]["members"], pls):
                mem["cue_role"] = p.get("cue_role")
                mem["role_source"] = p.get("role_source")
    for side, refs in (("left", lr), ("right", rr)):
        for mem, r in zip(out[side]["members"], refs):
            if _rat_of(r) is not None:
                mem["rat"] = _rat_of(r)

    dfs = set()
    for byw in out["cells"].values():
        for panel in byw.values():
            for c in panel.values():
                if c.get("df") is not None and c.get("p") is not None:
                    dfs.add(c["df"])
    n_rats = None
    if matched:
        n_rats = len(rats)
        mem_of = {}
        for side, pls, refs, names in (("left", L0, lr, lnames),
                                       ("right", R0, rr, rnames)):
            for p, r, nm in zip(pls, refs, names):
                role_key = p.get("cue_role") if contrast == "roles" else None
                mem_of[(_rat_of(r), side, role_key)] = _ref_out(p, r, nm)
        rows = []
        for rat, _slots in rats:
            for ro in (ROLES if contrast == "roles" else (None,)):
                row = {"rat": rat, "left": mem_of.get((rat, "left", ro)),
                       "right": mem_of.get((rat, "right", ro))}
                if ro:
                    row["cue_role"] = ro
                rows.append(row)
        out["matched"] = rows
        out["rats"] = n_rats
    if contrast == "roles":
        out["cell_sides"] = {
            "left": "no-food pair change (%s → %s)" % (
                labels.get("left") or "left", labels.get("right") or "right"),
            "right": "food pair change (%s → %s)" % (
                labels.get("left") or "left", labels.get("right") or "right")}
    if contrast == "baseline":
        kind = out.get("kind")
        used = []
        for side, pls, refs in (("left", L0, lr), ("right", R0, rr)):
            bs = ((baselines or {}).get(side) or [])
            brs = ((baseline_refs or {}).get(side) or [])
            for i, (p, r) in enumerate(zip(pls, refs)):
                b = bs[i] if i < len(bs) else None
                if b is None:
                    continue
                br = brs[i] if i < len(brs) else None
                used.append({"for": _ref_get(r, "artifact_id", "id"),
                             "side": side,
                             "ref": _ref_out(b, br, _ref_get(br, "nickname",
                                                             "name")
                                             or (b.get("source") or {})
                                             .get("session_label"))})
        out["baseline"] = {"from": BASELINE_FROM,
                           "windows": [[d, w] for d, w in
                                       CONTRAST_WINDOWS.get(kind, ())],
                           "circuits": used}
    out["analysis_say"] = say_analysis(opts, rats=n_rats, dfs=dfs,
                                       role=role, bh_tests=bh_tests)
    if bh_tests is not None:
        out["bh_tests"] = bh_tests
    scope = ("BH across all windows and methods" if bh_scope == "artifact"
             else "BH across each panel")
    if matched:
        out["method"] = ("DerSimonian-Laird random effects over the rats' "
                         "within-rat changes; %s; %s"
                         % ("Hartung-Knapp t" if test_id == "hk"
                            else "z" if test_id == "z" else test_id, scope))
    else:
        out["method"] = "DerSimonian-Laird random effects; " + scope
    notes = []
    if test_id == "hk":
        notes.append(HK_NOTE)
    elif matched:
        notes.append(Z_NOTE_RATS)
    else:
        notes.append(Z_NOTE)
    if contrast == "baseline":
        notes.append("cue − baseline is taken per cue pair, window by "
                     "window, each window with its own wire per region (the "
                     "lowest-numbered one usable there), so a pair whose "
                     "wire changed between the baseline and the cue window "
                     "differences two wires.")
    out["notes"] = notes
    if matched and n_rats and n_rats < 2 and test_id == "hk":
        out["warn"].append("One rat: Hartung-Knapp cannot test anything with "
                           "fewer than two rats.")
    return out


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
    out = {"left_k": len(((p.get("left") or {}).get("members")) or []),
           "right_k": len(((p.get("right") or {}).get("members")) or []),
           "kind": p.get("kind"), "cue_types": p.get("cue_types"),
           "equivalence": len(p.get("cue_equivalence") or []),
           "cells": cells, "tests": tests, "q_lt_05": sig}
    if p.get("design"):
        # Only a non-default drift has these; a default one's summary is
        # what it always was.
        out.update(design=p.get("design"),
                   test=(p.get("test") or {}).get("id"),
                   bh_scope=p.get("bh_scope"), contrast=p.get("contrast"),
                   pooled_by=p.get("pooled_by"), cue_role=p.get("cue_role"),
                   rats=p.get("rats"), band=(p.get("params") or {}).get("band"))
    return out
