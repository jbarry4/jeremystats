"""
recipe.py -- what it would take to make this again, for every tool.

A result in Results/ is evidence, and six months later the question is always
the same: which recording, which seconds of it, which settings. `rebuild.py`
answers that well -- it packs the complete layout onto the run record, audits
it against the machine as it is *now*, and walks the steps one at a time
saying what each actually did.

It answers it for figures. Only figures. Panorama, Incisor, ToolKit, the deck
exporter and every curation and layer export get nothing, and the button that
would offer it is hidden rather than empty:

    if (!r.run_id || r.kind !== 'figure') return null;

So this is the registry the gate should have been asking. A tool says what it
can do about its own runs, and the Results view asks the registry instead of
asking whether the word "figure" appears.

WHAT A TOOL REGISTERS

    kind      the run kind this handles -- "figure", "panorama", "toolkit"
    label     what the button should say
    plan      run -> {recipe, steps, verdict}. What it would take, and what
              stands in the way, checked before anything is done. A missing
              drive is a sentence in the dialog rather than a failure four
              steps in.
    restore   optional. run -> opens the tool with everything filled in.
              Client-side for most tools, so the registry only says whether
              one exists and the browser does the work.
    rerun     optional. run -> compute it again and compare.

WHAT "CAN THIS BE REBUILT" ACTUALLY MEANS

Three different answers, and conflating them is why the button was hidden:

    replay    the settings are written down, so the tool can be re-opened
              with them. Everything with a run record can do this.
    rebuild   the inputs are still reachable, so it can be made again.
    verify    the answer was kept, so a new run can be compared against the
              old numbers rather than against a picture of them.

A tool that keeps its answers -- see toolresults.py -- can do the third, and
that is the one that makes an archive trustworthy: not "here is a figure" but
"this still comes out the same, checked on Tuesday".
"""
from __future__ import annotations

# kind -> handler dict. Registered at import time by whoever owns the tool.
_HANDLERS = {}


def register(kind, label, plan, restore=None, rerun=None, verify=None):
    """Say what can be done about runs of this kind."""
    _HANDLERS[kind] = {
        "kind": kind,
        "label": label,
        "plan": plan,
        "restore": restore,
        "rerun": rerun,
        "verify": verify,
    }
    return _HANDLERS[kind]


def handler_for(run):
    """The handler for this run, or None."""
    if not run:
        return None
    return _HANDLERS.get(run.get("kind"))


def kinds():
    return sorted(_HANDLERS)


def offer(run):
    """What the Results view should put on this result, without doing any of it.

    Cheap on purpose: it is asked once per card in a grid of several hundred,
    so it reads the run record and nothing else. Whether the recording is
    actually reachable is the plan's question, and the plan is what the button
    opens.
    """
    h = handler_for(run)
    if not h:
        return None
    return {
        "kind": h["kind"],
        "label": h["label"],
        "can_replay": True,
        "can_restore": bool(h["restore"]),
        "can_rerun": bool(h["rerun"]),
        "can_verify": bool(h["verify"]),
    }


def plan_for(run):
    """The audited plan: what it would take, and what stands in the way."""
    h = handler_for(run)
    if not h:
        raise LookupError(
            "Nothing knows how to rebuild a %s. The tools that do are: %s."
            % (run.get("kind") or "record", ", ".join(kinds()) or "none"))
    return h["plan"](run)


def verify(run):
    """Compute it again and say whether it still comes out the same.

    Numeric, not pixel: a tool that kept its answers is compared against the
    numbers a figure was drawn from, so a rendering change is not mistaken for
    a result changing, and a result changing is not hidden by a rendering that
    happens to look the same.
    """
    h = handler_for(run)
    if not h or not h["verify"]:
        raise LookupError(
            "A %s does not keep its answers, so there is nothing to check a "
            "new run against." % (run.get("kind") or "record"))
    return h["verify"](run)
