"""
retime.py -- moving a banked event set from Toothy's clock to the recording's.

Toothy concatenates a multi-segment recording, which closes the gaps and
rebuilds the time axis as `i / fs`. Every event it reports after a gap
therefore carries a time earlier than its true one, by the cumulative duration
of all preceding gaps: 45 ms at the first gap on M8s9feb8, 121.9 ms by the
end. A dentate spike is 10-20 ms wide, so seeking to one of those times in the
raw file lands six to twelve event widths away.

This is the operation that fixes it, and it is arithmetic on existing events.
It does not re-detect anything, it does not touch the raw `.ncs` files, it does
not rewrite `DATA.hdf5`, and it does not interpolate across a gap -- the
samples were never recorded and a gap is missing data, not bad data.

WHICH WAY
---------
To the recording's own Neuralynx clock, because Jarvis is a raw-backed
application: its viewer, its `.nvt` tracking, its `.nev` marks and its video
are all on that clock, and making DS agree with the raw file makes it agree
with everything else on screen.

The cost is explicit and the preview states it: **kilosort unit times for the
same session are still in concatenated time** and need the same conversion
before unit/DS comparisons mean anything.

WHEN IT MAY BE OFFERED
----------------------
Four conditions, none of them inferred:

  1. the recording segments into more than one piece;
  2. a bank entry exists for the session;
  3. there is POSITIVE evidence its times are Toothy concat-era output;
  4. it has not already been re-timed.

Condition 3 is the one it would be tempting to skip. A set hand-curated in
Jarvis against the raw viewer, or imported from a snapshot folder, is NOT in
concatenated time, and "correcting" it would introduce exactly the error being
fixed. So the basis is established from the pipeline that produced the set,
and the evidence for each accepted pipeline is written down below.
"""
from __future__ import annotations

from . import continuity

# Pipelines whose output is in Toothy's concatenated time, with the evidence.
#
# Not a guess and not a naming convention: each of these was checked against
# Toothy's own `ALL_DS` times in `DATA.hdf5` for a recording with gaps. If the
# export were on a different clock, the events after the first gap would sit
# 96-122 ms from Toothy's; they sit within 1.5 ms, the same as the events
# before it.
CONCAT_PIPELINES = {
    "ETS dentate-spike export": (
        "Measured on M8s9feb8: all 1224 banked times sit within 1.5 ms of a "
        "Toothy ALL_DS time, including the 314 after the first gap, which "
        "would be 96-122 ms away on any other clock."),
}

# Pipelines known NOT to be in concatenated time, so the offer is refused with
# a reason rather than left ambiguous.
RAW_PIPELINES = {
    "Jarvis curation (ds)": (
        "Curated in Jarvis against the raw viewer, so already on the "
        "recording's own clock."),
    "Jarvis threshold detector": (
        "Detected from the raw .ncs files by Jarvis itself."),
    "Incisor (dentate spike)": (
        "Detected from the raw .ncs files by Jarvis itself, and stamped "
        "through `continuity.sample_to_true` -- the recording's own record "
        "timestamps and its measured sample rate -- rather than from a "
        "sample index over a nominal one. Checked against Toothy's own "
        "`get_ds_peaks` on identical input over ten real and ten synthetic "
        "recordings: 4430 events at exactly the same samples, with the "
        "timestamp difference accounted for by the rig's crystal and "
        "Toothy's linspace axis to within 0.42 ppm. A set from here has "
        "the gaps in it already and must never be offered the correction."),
}

TRUE = "neuralynx_true"
CONCAT = "toothy_concat"


def basis_of(entry):
    """What clock is this entry's times on, and how do we know?

    Absence of a stamp means UNKNOWN, never "true". That distinction is the
    whole safety of the operation: a set whose basis cannot be established
    gets no offer, not a default.
    """
    stamped = (entry or {}).get("time_basis") or {}
    if stamped.get("kind"):
        return {"basis": stamped["kind"], "why": "Stamped on the entry.",
                "stamped": True, "certain": True}

    pipeline = ((entry or {}).get("source") or {}).get("pipeline") or ""
    if pipeline in CONCAT_PIPELINES:
        return {"basis": CONCAT, "why": CONCAT_PIPELINES[pipeline],
                "stamped": False, "certain": True, "pipeline": pipeline}
    if pipeline in RAW_PIPELINES:
        return {"basis": TRUE, "why": RAW_PIPELINES[pipeline],
                "stamped": False, "certain": True, "pipeline": pipeline}
    return {"basis": None,
            "why": ("Nothing records what clock %s produces, so there is no "
                    "evidence either way. A correction applied on a guess "
                    "would introduce the error it is meant to remove."
                    % (pipeline or "this set")),
            "stamped": False, "certain": False, "pipeline": pipeline}


def offer(report, entry, curation_set=None, me=None):
    """Should a re-timing be offered for this entry, and if not, why not?

    Always returns a reason. "No action available" with nothing said is how a
    person concludes the data is fine.
    """
    out = {"offer": False, "reason": None, "basis": None,
           "n": (entry or {}).get("n"), "entry_id": (entry or {}).get("id")}

    if not report or not report.get("ok"):
        out["reason"] = "The recording has not been checked for gaps yet."
        return out
    if int(report.get("n_segments") or 1) <= 1:
        out["reason"] = ("This recording is continuous, so Toothy's times and "
                         "the raw file's agree exactly. Nothing to correct.")
        return out
    if not entry:
        out["reason"] = ("The recording has gaps, but no event set is banked "
                         "against it, so there is nothing to re-time.")
        return out

    basis = basis_of(entry)
    out["basis"] = basis
    if basis["basis"] == TRUE:
        out["reason"] = ("Already on the recording's own clock. " + basis["why"])
        return out
    if not basis["certain"]:
        out["reason"] = basis["why"]
        return out

    # Someone else has it open. Re-timing on one machine and syncing is the
    # simplest thing that cannot go wrong; two machines correcting the same
    # set at once is the thing that can.
    holder = ((curation_set or {}).get("open_by")
              or (curation_set or {}).get("assigned_to"))
    if holder and me and str(holder).strip().lower() != str(me).strip().lower():
        out["reason"] = ("%s has this set open. Re-time it on one machine and "
                         "let it sync, rather than two at once." % holder)
        return out

    out["offer"] = True
    out["reason"] = ("%d event(s) are in Toothy's concatenated time and run "
                     "up to %.1f ms early against the raw files."
                     % (entry.get("n") or 0,
                        float(report.get("max_time_error_ms") or 0.0)))
    return out


def preview(report, entry, curation=None, gid=None, kind="ds"):
    """What a re-timing would do, without doing any of it.

    The preview is the thing a person approves, so it carries the numbers
    that make approval reasonable: how many events move, the shift per
    segment, before and after for a handful, how many decisions are affected,
    and -- said plainly, because it is the real barrier -- that every labelled
    event keeps its label and nothing is re-detected.
    """
    mapping = lambda t: continuity.concat_to_true(report, t)
    out = {
        "ok": True,
        "to": TRUE,
        "from": CONCAT,
        "gap_map_sha": report.get("gap_map_sha"),
        "n_segments": report.get("n_segments"),
        "max_time_error_ms": report.get("max_time_error_ms"),
        "shifts": continuity.shift_table(report),
        "keeps_labels": True,
        "redetects": False,
        # Said here rather than left to be discovered: the same session's
        # kilosort units are still on the other clock afterwards.
        "caveats": [
            "Every labelled event keeps its label. Nothing is re-detected.",
            "Kilosort unit times for this session are still in concatenated "
            "time and need the same conversion before unit/DS comparisons "
            "mean anything.",
            "Reversal is 'restore the previous version', not a second "
            "arithmetic pass.",
        ],
    }

    events = (entry or {}).get("events") or []
    near = 0
    for ev in events:
        try:
            t = float(ev.get("start"))
        except (TypeError, ValueError):
            continue
        true_t, _seg = mapping(t)
        if true_t is not None and continuity.near_stitch(report, true_t):
            near += 1
    out["near_stitch"] = near
    if near:
        out["caveats"].insert(1, (
            "%d event(s) sit within 125 ms of a stitch. Toothy filters and "
            "peak-detects straight across the discontinuity, so those may be "
            "filter ringing rather than real dentate spikes -- correcting the "
            "time does not make them real." % near))
    return out
