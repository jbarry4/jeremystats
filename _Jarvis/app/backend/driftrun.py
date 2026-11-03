"""driftrun.py -- running The Arc's Drift: members, pre-flight, local, VACC.

`drift.py` says what a drift IS: a pure function from two groups of circuit
payloads to the arc.drift/1 payload. This says how one gets MADE from the
artifact store, so that `app.py` only holds thin routes:

  members(host, ...)   the circuit artifacts that can be put on a side,
                       every version of each, grouped by rat and phase
  check(host, body)    the pre-flight: are these two groups comparable, and
                       if not which field disagrees and why -- and what it
                       would cost -- before anything is computed
  prepare(host, body)  the same, plus the payloads, ready to build
  start_local / start_vacc
                       a cfc job either way, so the panel follows a local
                       run and a cluster run with the same poll
  file_drift           put + cite: the one place a drift is filed

PINNING

A drift's inputs are `[{"kind": "artifact", "id", "version", "version_id",
"digest", "side"}]`: every circuit version it read, by the version id
(numbers clash across machines -- arc_contracts.md 0b). Filing CITES each
of them, so those circuit versions cannot be deleted while the drift lives.

RE-RUNNING CONFIRMS

The members of each side are sorted by (artifact id, version id) before the
build, so the order somebody dragged them in does not change the payload.
The drift's subject key is built from those pins, the cue type, the kind and
any recorded cue equivalence (artifacts._drift_key), so the same comparison
finds the same artifact, and `put` stamps `confirmed` when the numbers are
the same. The one thing in the payload that is a moment in time -- WHEN a
person said two cue types were equivalent -- is carried over from the
artifact's current version when the same equivalence is asked for again, so
restating a decision does not read as a new answer.

THE ANALYSIS CHOICES (arc_contracts.md 7.4)

The body may carry `design` ("independent" | "matched"), `test` ("z" |
"hk"), `bh_scope` ("panel" | "artifact") and `contrast` (null | "baseline"
| "roles"); absent is today's behaviour, and then nothing here or in the
payload differs from before. The matched design pairs members by rat
(`subject.mouse`, as `r<mouse>`; `<project> r<mouse>` when the members span
projects). For cue - baseline, each TRANSITION member needs the state
circuit of the same recording, pairing and band: named inline on the member
(`{id, version_id, baseline: {id, version_id}}`), or in `baseline: {left:
[{id, version_id, for: <member id>}], right: [...]}`, or -- when neither
names it -- the one live such circuit in the store, at its current version.
Either way it is PINNED, listed in the pre-flight, filed as an input with
`role: "baseline"`, and cited. A non-default drift's subject carries
`analysis` (and `baseline` pins), so it is a different artifact from the
default drift of the same circuits, never a version of it.

THE NODE

`run_node` is what `vacc_run.py` calls for `tool == "drift"`: the circuit
payloads travel in the spec (without their per-pair `values`, which pooling
never reads), the node calls the same `drift.build`, and the answer comes
back to be filed here. The node never sees the artifact store.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone

from . import cfc, drift

STAGE = "drift cells"
_LOCK = threading.RLock()


class DriftRunError(Exception):
    """Refused, with a sentence for a person and an HTTP code."""

    def __init__(self, message, code=400, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


class Host(object):
    """What app.py hands in.

      artifacts            the ARTIFACTS store
      provenance()         -> STORE.provenance()
      activity(rows)       -> STORE.record_activity
      vacc_status()        -> vacc.status()
      vacc_cfg()           -> vacc.load_config(LOGS_DIR)
      push_code()          -> vacc.push_code(cfg, APP_DIR)
      vacc_run(spec, seconds, tool_steps) -> a vaccrun.VaccRun for tool "drift"
    """

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _prov(host):
    try:
        return dict(host.provenance() or {})
    except Exception:                                    # noqa: BLE001
        return {}


def say_s(s):
    if s is None:
        return None
    s = float(s)
    if s < 1:
        return "under a second"
    if s < 90:
        return "%d s" % max(1, int(round(s)))
    return "%d min" % int(round(s / 60.0))


# ==========================================================================
# The members on offer
# ==========================================================================
def params_digest(params, kind):
    """The analysis parameters that change a circuit's numbers FOR ITS KIND,
    as 8 hex characters. Two circuits with the same digest can be compared
    on parameters; `drift.compatible` is still the test.

    The band-mode fields (drift.MODE_PARAMS) join only when set, so a
    circuit made before bands keeps the digest it always had, and a theta
    band circuit -- the same low/high/max_lag as the old default -- does
    not read as the same analysis."""
    keep = {k: (params or {}).get(k) for k in drift.number_params(kind)}
    for k in drift.MODE_PARAMS:
        if (params or {}).get(k) is not None:
            keep[k] = params[k]
    blob = json.dumps(keep, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:8]


def _vrow_out(row, kind, current_id):
    n = row.get("n_summary") or {}
    return {"v": row.get("v"), "version_id": row.get("id"),
            "digest": row.get("digest"), "at": row.get("at"),
            "by": row.get("by"), "machine": row.get("machine"),
            "here": row.get("here"), "n_pairs": n.get("n_pairs"),
            "n_grey": n.get("n_grey"),
            "params_digest": params_digest(row.get("params"), kind),
            "confirmed": len(row.get("confirmed") or []),
            "current": row.get("id") == current_id,
            "band": n.get("band"), "cue_role": n.get("cue_role")}


def _band_label(band):
    if band in (None, ""):
        return None
    try:
        from . import circuit
        return circuit.band_label(band)
    except Exception:                                    # noqa: BLE001
        return str(band)


def _group(s):
    rat = ("r%s" % s["mouse"]) if s.get("mouse") is not None else None
    ph = None
    if s.get("phase"):
        ph = "%s%s" % (s["phase"], "" if s.get("phase_n") is None
                       else s["phase_n"])
    bits = [b for b in (s.get("project"), rat, ph) if b]
    return " ".join(bits) or (s.get("session_label") or s.get("gid")
                              or "Unfiled")


def members(host, kind=None, cue_type=None, chosen=None):
    """Every live circuit artifact a side can take, with every version.

    `chosen`: ["<id>" | "<id>@<version_id>", ...] -- the set already on the
    two sides. Each row then says whether its current version fits that set
    (same kind, same number-changing parameters, same cue type) and, when
    not, why in words; `cue_only` marks a row that differs ONLY by cue type,
    which the panel can offer to treat as equivalent.
    """
    arts = host.artifacts
    rows = []
    for s in arts.list(kind="circuit"):
        subj = s.get("subject") or {}
        k = subj.get("window_kind")
        if kind and k != kind:
            continue
        if cue_type and subj.get("cue_type") != cue_type:
            continue
        cur = s.get("current") or {}
        vers = sorted((_vrow_out(v, k, cur.get("id"))
                       for v in s.get("versions") or []),
                      key=lambda v: (-(v["v"] or 0), v["at"] or ""))
        curo = next((v for v in vers if v["current"]), vers[0] if vers
                    else {})
        band = subj.get("band") if subj.get("band") is not None \
            else curo.get("band")
        role = subj.get("cue_role") or curo.get("cue_role")
        rows.append({
            "artifact_id": s["id"], "name": s.get("name"),
            "nickname": s.get("nickname"),
            "gid": subj.get("gid"), "project": subj.get("project"),
            "mouse": subj.get("mouse"), "session": subj.get("session"),
            "phase": subj.get("phase"), "phase_n": subj.get("phase_n"),
            "run": subj.get("run"), "session_label": subj.get("session_label"),
            "cue_type": subj.get("cue_type"),
            "cue_label": subj.get("cue_label")
            or _cue_label(subj.get("cue_type")),
            "kind": k, "group": _group(subj),
            "version": curo.get("v"), "version_id": curo.get("version_id"),
            "digest": curo.get("digest"), "n_pairs": curo.get("n_pairs"),
            "params_digest": curo.get("params_digest"),
            "here": curo.get("here"),
            "cited": s.get("cited_active") or 0,
            "versions": vers,
            "band": band, "band_label": _band_label(band),
            "cue_role": role,
        })
    rows.sort(key=lambda r: (r["group"], str(r.get("session") or ""),
                             r.get("cue_type") or "", r.get("kind") or ""))

    sig = None
    want = [str(c) for c in (chosen or []) if c]
    if want:
        by_id = {r["artifact_id"]: r for r in rows}
        for c in want:
            aid, _, vid = c.partition("@")
            r = by_id.get(aid)
            if not r:
                continue
            v = next((x for x in r["versions"] if x["version_id"] == vid),
                     None) if vid else None
            v = v or {"params_digest": r["params_digest"]}
            sig = {"kind": r["kind"], "cue_type": r["cue_type"],
                   "cue_label": r["cue_label"], "cue_role": r["cue_role"],
                   "params_digest": v["params_digest"], "name":
                   r.get("nickname") or r.get("name")}
            break
    chosen_ids = {c.partition("@")[0] for c in want}
    for r in rows:
        r["chosen"] = r["artifact_id"] in chosen_ids
        if sig is None:
            r["compatible"], r["why"], r["cue_only"] = None, [], False
            continue
        why = []
        if r["kind"] != sig["kind"]:
            why.append("it is a %s circuit and the chosen ones are %s"
                       % (r["kind"], sig["kind"]))
        if r["params_digest"] != sig["params_digest"]:
            why.append("it was made at other analysis parameters than %s"
                       % sig["name"])
        if r.get("cue_role") and sig.get("cue_role"):
            # Both carry a role (7.2): the role is what is compared, the
            # counterbalanced pairing is not.
            cue = False
            if r["cue_role"] != sig["cue_role"]:
                why.append("it is the %s and the chosen ones are the %s"
                           % (drift.ROLE_SAY.get(r["cue_role"], r["cue_role"]),
                              drift.ROLE_SAY.get(sig["cue_role"],
                                                 sig["cue_role"])))
        else:
            cue = r["cue_type"] != sig["cue_type"]
        if cue:
            why.append("it is %s and the chosen ones are %s"
                       % (r["cue_label"], sig["cue_label"]))
        r["compatible"] = not why
        r["why"] = why
        r["cue_only"] = cue and len(why) == 1
    groups = []
    for r in rows:
        if not groups or groups[-1]["group"] != r["group"]:
            groups.append({"group": r["group"], "ids": []})
        groups[-1]["ids"].append(r["artifact_id"])
    return {"rows": rows, "groups": groups, "signature": sig}


def _cue_label(cue_type):
    try:
        from . import circuit
        return circuit.cue_label(cue_type)
    except Exception:                                    # noqa: BLE001
        return cue_type


# ==========================================================================
# Resolving and pinning the members
# ==========================================================================
def _pin(host, ref, side):
    """One member: its record, the exact version row, and the payload."""
    arts = host.artifacts
    if not isinstance(ref, dict):
        raise DriftRunError("Each member is {id, version_id}; got %r." % (ref,))
    aid = ref.get("id") or ref.get("artifact_id")
    want = ref.get("version_id") or ref.get("version")
    if not aid:
        raise DriftRunError("A member of the %s group names no artifact."
                            % side)
    try:
        rec, row = arts.payload_version(aid, want)
    except Exception as exc:                             # noqa: BLE001
        raise DriftRunError("Circuit %s: %s" % (aid, exc), 409)
    if not rec:
        raise DriftRunError("There is no artifact %s (in the %s group)."
                            % (aid, side), 404)
    if rec.get("kind") != "circuit":
        raise DriftRunError("%s is a %s, not a circuit: a drift compares "
                            "circuits." % (rec.get("nickname") or
                                           rec.get("name"), rec.get("kind")))
    if rec.get("deleted"):
        raise DriftRunError("%s was deleted, so it cannot be compared."
                            % (rec.get("nickname") or rec.get("name")), 409)
    try:
        payload = arts.payload(aid, row["id"])
    except Exception as exc:                             # noqa: BLE001
        raise DriftRunError("%s v%s: %s" % (rec.get("nickname") or
                                            rec.get("name"), row.get("v"),
                                            exc), 409)
    if payload is None:
        raise DriftRunError(
            "%s v%s was made on %s and its payload has not reached this "
            "machine yet, so it cannot be read here. It arrives with the next "
            "sync or git pull." % (rec.get("nickname") or rec.get("name"),
                                   row.get("v"), row.get("machine")
                                   or "another machine"), 409)
    subj = rec.get("subject") or {}
    return {
        "ref": {"kind": "artifact", "id": rec["id"], "version": row["v"],
                "version_id": row["id"], "digest": row["digest"],
                "side": side},
        "name": rec.get("name"), "nickname": rec.get("nickname"),
        "gid": subj.get("gid"), "payload": payload,
        "subject": subj, "asked": ref,
    }


def _pins(host, refs, side):
    got = [_pin(host, r, side) for r in (refs or [])]
    # Order does not change the answer: sorted by the pin itself.
    got.sort(key=lambda p: (p["ref"]["id"], p["ref"]["version_id"]))
    return got


def _drift_refs(pins):
    """What drift.build is handed as refs (and names members by). `rat`
    rides along for the within-rat design; the default build never reads
    it, so a default drift's payload is unchanged."""
    out = []
    for p in pins:
        r = {"artifact_id": p["ref"]["id"], "version": p["ref"]["version"],
             "version_id": p["ref"]["version_id"],
             "digest": p["ref"]["digest"],
             "name": p.get("nickname") or p.get("name")}
        if p.get("rat") is not None:
            r["rat"] = p["rat"]
        out.append(r)
    return out


def _label_rats(*groups):
    """Each pin's rat, from its circuit's subject: `r<mouse>`, and
    `<project> r<mouse>` when the pins span more than one project -- mouse
    numbers restart per project, so r7 of two projects is two animals."""
    pins = [p for g in groups for p in (g or [])]
    projects = {(p.get("subject") or {}).get("project") for p in pins}
    for p in pins:
        s = p.get("subject") or {}
        if s.get("mouse") in (None, ""):
            p["rat"] = None
        elif len(projects) > 1:
            p["rat"] = "%s r%s" % (s.get("project"), s["mouse"])
        else:
            p["rat"] = "r%s" % s["mouse"]


def _band_of(pin):
    s = pin.get("subject") or {}
    if s.get("band") is not None:
        return s["band"]
    P = pin.get("payload") or {}
    return P.get("band") if P.get("band") is not None \
        else (P.get("params") or {}).get("band")


def _opts(body):
    """The analysis choices (arc_contracts.md 7.4) from the body, validated;
    absent is today's behaviour."""
    b = body or {}
    try:
        return drift.options(b.get("design"), b.get("test"),
                             b.get("bh_scope"), b.get("contrast"))
    except drift.DriftError as exc:
        raise DriftRunError(" ".join(exc.reasons), 400, reasons=exc.reasons)


def _asked_baselines(body, side):
    """Baselines named in the body for one side: `baseline` (or
    `baselines`) as {left: [...], right: [...]} or a flat list; each
    {id, version_id, for?}. {member id: ref} for those with `for`, and the
    rest as a list to match by recording."""
    got = (body or {}).get("baseline")
    if got is None:
        got = (body or {}).get("baselines")
    if isinstance(got, dict):
        got = got.get(side) or []
    by_for, loose = {}, []
    for r in got or []:
        if not isinstance(r, dict):
            continue
        if r.get("for"):
            by_for[str(r["for"])] = r
        else:
            loose.append(r)
    return by_for, loose


def _baselines(host, body, left, right):
    """cue - baseline: for each TRANSITION member, the state circuit of the
    same recording, pairing and band, pinned -- as the body names it (inline
    on the member as `baseline`, or in `baseline` with `for`), else the one
    live such circuit in the store (its current version). Returns
    ({"left": [pin | None], "right": [...]}, [sentences])."""
    out, why = {"left": [], "right": []}, []
    store = None
    for side, pins in (("left", left), ("right", right)):
        by_for, loose = _asked_baselines(body, side)
        loose_pins = [_pin(host, r, side) for r in loose]
        for p in pins:
            P = p["payload"] or {}
            if P.get("kind") != "transition":
                out[side].append(None)
                continue
            asked = (p.get("asked") or {}).get("baseline") \
                or by_for.get(p["ref"]["id"])
            got = None
            if asked:
                got = _pin(host, asked, side)
            else:
                band = _band_of(p)
                hits = [b for b in loose_pins
                        if (b["payload"] or {}).get("kind") == "state"
                        and b["gid"] == p["gid"]
                        and (b["payload"] or {}).get("cue_type")
                        == P.get("cue_type") and _band_of(b) == band]
                if not hits and not loose:
                    if store is None:
                        store = [s for s in host.artifacts.list(kind="circuit")
                                 if not s.get("deleted")]
                    hits = []
                    for s in store:
                        subj = s.get("subject") or {}
                        cur = s.get("current") or {}
                        sb = subj.get("band") if subj.get("band") is not None \
                            else (cur.get("n_summary") or {}).get("band")
                        if (subj.get("window_kind") == "state"
                                and subj.get("gid") == p["gid"]
                                and subj.get("cue_type") == P.get("cue_type")
                                and sb == band):
                            hits.append(s)
                    if len(hits) > 1:
                        why.append(
                            "%s: there are %d state circuits of that "
                            "recording, pairing and band to take the baseline "
                            "from (%s); name the one to use." % (
                                p.get("nickname") or p.get("name"), len(hits),
                                ", ".join(h.get("nickname") or h.get("name")
                                          for h in hits)))
                        hits = []
                    elif hits:
                        hits = [_pin(host, {"id": hits[0]["id"],
                                            "version_id": (hits[0].get(
                                                "current") or {}).get("id")},
                                     side)]
                got = hits[0] if len(hits) == 1 else None
            if got is not None:
                got["ref"] = dict(got["ref"], role="baseline",
                                  **{"for": p["ref"]["id"]})
            out[side].append(got)
    return out, why


def _base_payloads(bases):
    if not bases:
        return None
    return {s: [None if b is None else b["payload"] for b in bases.get(s, [])]
            for s in ("left", "right")}


def _base_refs(bases):
    if not bases:
        return None
    return {s: [None if b is None else _drift_refs([b])[0]
                for b in bases.get(s, [])] for s in ("left", "right")}


def _base_list(bases):
    return [b for s in ("left", "right") for b in (bases or {}).get(s, [])
            if b is not None]


def _n_cells(payloads, contrast=None):
    if not payloads:
        return 0
    first = payloads[0]
    n = len(first.get("region_order") or [])
    wins = len(first.get("windows") or [])
    if contrast == "baseline":
        wins = len(drift.CONTRAST_WINDOWS.get(first.get("kind"), ()))
    return (n * (n - 1) // 2 * wins * len(first.get("methods") or []))


def _suggest(left, right):
    """If the only refusal is the cue type, the equivalence that would lift
    it: every distinct pairing joined to the first one seen."""
    types = []
    for p in left + right:
        ct = (p["payload"] or {}).get("cue_type")
        if ct and ct not in types:
            types.append(ct)
    return [{"from": types[0], "to": t} for t in types[1:]]


def _cue_rows(left, right):
    out = []
    for side, pins in (("left", left), ("right", right)):
        for p in pins:
            P = p["payload"] or {}
            ct = P.get("cue_type")
            if not any(r["cue_type"] == ct and r["side"] == side for r in out):
                out.append({"side": side, "cue_type": ct,
                            "cue_label": P.get("cue_label") or ct})
    return out


# ==========================================================================
# The pre-flight
# ==========================================================================
def vacc_ok(st):
    """(can, why) from vacc.status(). A cluster nobody has probed yet is
    not "unreachable" -- `available` is False until the first probe, and
    reading that as a refusal would be absent read as negative. Only a
    probe that FAILED refuses; the run itself finds out otherwise."""
    st = st or {}
    if not st.get("configured"):
        return False, "No VACC account is set up on this computer."
    if st.get("available") is False and st.get("checked_at"):
        return False, st.get("why") or "The cluster is not reachable."
    return True, None


def cost(host, n_circuits, n_cells):
    rate = cfc.rate_for(STAGE)
    local_s = round(n_cells * rate, 2)
    st = {}
    try:
        st = host.vacc_status() or {}
    except Exception:                                    # noqa: BLE001
        st = {}
    vacc_can, vacc_why = vacc_ok(st)
    vacc_s = round(n_cells * cfc.rate_for(STAGE, "vacc:node"), 2) \
        if vacc_can else None
    sentence = ("%d circuit%s, %d cell%s to pool and test; %s here"
                % (n_circuits, "" if n_circuits == 1 else "s", n_cells,
                   "" if n_cells == 1 else "s",
                   "under a second" if local_s < 1
                   else "about " + say_s(local_s)))
    if vacc_can:
        sentence += ("; on the VACC the same arithmetic plus sending the "
                     "circuits and the queue wait, which is usually minutes")
    return {"n_circuits": n_circuits, "n_cells": n_cells,
            "local_s": local_s, "local_can": True,
            "vacc_s": vacc_s, "vacc_can": vacc_can, "vacc_why": vacc_why,
            "sentence": sentence + "."}


def _labels(body):
    lab = body.get("labels") or {}
    if isinstance(lab, (list, tuple)):
        lab = {"left": lab[0] if lab else None,
               "right": lab[1] if len(lab) > 1 else None}
    out = {}
    for s in ("left", "right"):
        v = str(lab.get(s) or "").strip()
        out[s] = v[:80] or ("Left" if s == "left" else "Right")
    return out


def check(host, body):
    """{compatible, reasons, cue_only, suggest, cue_types, warn, cost,
    members} -- stated before anything is computed. Never raises for an
    incompatible set: that is an answer, not an error."""
    body = body or {}
    left = _pins(host, body.get("left"), "left")
    right = _pins(host, body.get("right"), "right")
    _label_rats(left, right)
    L = [p["payload"] for p in left]
    R = [p["payload"] for p in right]
    eq = body.get("cue_equivalence") or []
    try:
        eq = drift.clean_equivalence(eq)
        opts = drift.options(body.get("design"), body.get("test"),
                             body.get("bh_scope"), body.get("contrast"))
    except drift.DriftError as exc:
        return {"compatible": False, "reasons": exc.reasons,
                "cue_only": False, "suggest": [], "cue_types": [],
                "warn": [], "cost": cost(host, len(L) + len(R), 0),
                "members": _members_out(left, right)}
    bases, bwhy = ({}, [])
    if opts["contrast"] == "baseline":
        bases, bwhy = _baselines(host, body, left, right)
    kw = dict(design=opts["design"], contrast=opts["contrast"],
              baselines=_base_payloads(bases), test=opts["test"])
    ok, reasons = drift.compatible(L, R, _drift_refs(left),
                                   _drift_refs(right), eq, **kw)
    if bwhy:
        ok, reasons = False, bwhy + reasons
    cue_only, suggest = False, []
    if not ok and L and R:
        trial = _suggest(left, right)
        if trial:
            ok2, _r2 = drift.compatible(L, R, _drift_refs(left),
                                        _drift_refs(right), eq + trial, **kw)
            cue_only = ok2 and not bwhy
            suggest = trial if cue_only else []
    warn = []
    for side, pins in (("left", left), ("right", right)):
        if len(pins) == 1:
            warn.append("The %s group is %s." % (side, drift.K1_SAY))
    out = {"compatible": ok, "reasons": reasons, "cue_only": cue_only,
           "suggest": suggest, "cue_types": _cue_rows(left, right),
           "equivalence": eq, "warn": warn,
           "cost": cost(host, len(L) + len(R) + len(_base_list(bases)),
                        _n_cells(L + R, opts["contrast"])),
           "members": _members_out(left, right)}
    # The analysis choices, as the result will state them, and -- before
    # anything is computed -- the rats the matched design pairs and the
    # baseline circuits a transition member will read.
    role = None
    roles = {P.get("cue_role") for P in L + R}
    if len(roles) == 1 and None not in roles and opts["contrast"] != "roles":
        role = next(iter(roles))
    rats = sorted({p.get("rat") for p in left + right
                   if p.get("rat") is not None}, key=drift._natkey)
    out["options"] = opts
    out["analysis_say"] = drift.say_analysis(
        opts, rats=len(rats) if opts["design"] == "matched" else None,
        role=role)
    if opts["design"] == "matched":
        out["matched"] = _matched_preview(left, right, opts["contrast"])
    if opts["contrast"] == "baseline":
        out["baselines"] = [dict(b["ref"], name=b.get("nickname")
                                 or b.get("name"), gid=b.get("gid"))
                            for b in _base_list(bases)]
    return out


def _matched_preview(left, right, contrast):
    """[{rat, cue_role?, left: name, right: name}] -- who is paired with
    whom, said before it runs."""
    by = {}
    for side, pins in (("left", left), ("right", right)):
        for p in pins:
            role = (p["payload"] or {}).get("cue_role") \
                if contrast == "roles" else None
            by.setdefault((p.get("rat"), role), {})[side] = dict(
                p["ref"], name=p.get("nickname") or p.get("name"))
    rows = []
    for (rat, role) in sorted(by, key=lambda k: (drift._natkey(k[0]),
                                                 str(k[1]))):
        row = {"rat": rat, "left": by[(rat, role)].get("left"),
               "right": by[(rat, role)].get("right")}
        if role:
            row["cue_role"] = role
        rows.append(row)
    return rows


def _members_out(left, right):
    def one(p):
        P = p["payload"] or {}
        return dict(p["ref"], name=p["name"], nickname=p["nickname"],
                    gid=p["gid"], n_pairs=P.get("n_pairs"),
                    cue_type=P.get("cue_type"), cue_label=P.get("cue_label"),
                    kind=P.get("kind"))
    return {"left": [one(p) for p in left], "right": [one(p) for p in right]}


# ==========================================================================
# Preparing a run
# ==========================================================================
def _carry_equivalence(host, key, eq):
    """Give each equivalence pair the by/at it was FIRST recorded with on
    this drift, when it was: the decision is the same decision."""
    have = host.artifacts.find("drift", key)
    if not have or not eq:
        return eq
    try:
        prev = host.artifacts.payload(have["id"]) or {}
    except Exception:                                    # noqa: BLE001
        return eq
    old = {(e.get("from"), e.get("to")): e
           for e in prev.get("cue_equivalence") or []}
    out = []
    for e in eq:
        o = old.get((e["from"], e["to"]))
        out.append(dict(e, by=o.get("by"), at=o.get("at")) if o else e)
    return out


def prepare(host, body):
    """Everything a run needs, refused (409, with the reasons) when the two
    groups cannot be compared."""
    body = body or {}
    left = _pins(host, body.get("left"), "left")
    right = _pins(host, body.get("right"), "right")
    if not left or not right:
        raise DriftRunError("Put at least one circuit on each side.", 400,
                            reasons=["The %s group is empty." % s
                                     for s, g in (("left", left),
                                                  ("right", right))
                                     if not g])
    _label_rats(left, right)
    L = [p["payload"] for p in left]
    R = [p["payload"] for p in right]
    prov = _prov(host)
    opts = _opts(body)
    try:
        eq = drift.clean_equivalence(body.get("cue_equivalence") or [])
    except drift.DriftError as exc:
        raise DriftRunError(" ".join(exc.reasons), 400, reasons=exc.reasons)
    eq = [dict(e, by=e.get("by") or prov.get("user") or "not recorded",
               at=e.get("at") or _now()) for e in eq]
    bases, bwhy = ({}, [])
    if opts["contrast"] == "baseline":
        bases, bwhy = _baselines(host, body, left, right)
    ok, reasons = drift.compatible(L, R, _drift_refs(left),
                                   _drift_refs(right), eq,
                                   design=opts["design"],
                                   contrast=opts["contrast"],
                                   baselines=_base_payloads(bases),
                                   test=opts["test"])
    if bwhy:
        ok, reasons = False, bwhy + reasons
    if not ok:
        raise DriftRunError("These two groups cannot be compared. "
                            + " ".join(reasons), 409, reasons=reasons)
    labels = _labels(body)
    first = L[0]
    # Only pairs that join cue types actually present -- what build keeps.
    used = {p.get("cue_type") for p in L + R}
    eq = [e for e in eq if e["from"] in used and e["to"] in used]
    subject = {
        "left": [dict(p["ref"], gid=p["gid"], name=p["nickname"] or p["name"])
                 for p in left],
        "right": [dict(p["ref"], gid=p["gid"], name=p["nickname"] or p["name"])
                  for p in right],
        "left_label": labels["left"], "right_label": labels["right"],
        "cue_type": first.get("cue_type"),
        "cue_label": first.get("cue_label") if len(used) == 1 else
        " ≡ ".join(sorted({p.get("cue_label") or p.get("cue_type")
                                for p in L + R})),
        "window_kind": first.get("kind"),
        "cue_equivalence": [{"from": e["from"], "to": e["to"]} for e in eq],
    }
    inputs = [p["ref"] for p in left] + [p["ref"] for p in right]
    base_pins = _base_list(bases)
    # What a non-default drift adds (7.4). Only then: a default drift's
    # subject -- and so its key and its name -- is what it always was.
    by_role = all(P.get("cue_role") not in (None, "") for P in L + R)
    if not drift.is_default(opts) or by_role:
        subject["analysis"] = dict(opts)
        roles = sorted({P.get("cue_role") for P in L + R} - {None})
        if by_role:
            role = roles[0] if len(roles) == 1 else None
            subject["cue_role"] = role
            subject["cue_label"] = (drift.ROLE_SAY.get(role, role) if role
                                    else "food pair − no-food pair")
        bands = {_band_of(p) for p in left + right}
        if len(bands) == 1 and None not in bands:
            subject["band"] = next(iter(bands))
            subject["band_label"] = _band_label(subject["band"])
        if opts["design"] == "matched":
            for side in ("left", "right"):
                for ref, p in zip(subject[side], left if side == "left"
                                  else right):
                    ref["rat"] = p.get("rat")
        if base_pins:
            subject["baseline"] = sorted(
                ({"id": b["ref"]["id"], "version_id": b["ref"]["version_id"],
                  "for": b["ref"]["for"], "side": b["ref"]["side"]}
                 for b in base_pins),
                key=lambda d: (d["side"], d["for"], d["id"]))
        # Inputs carry each member's role (7.4), and the baselines read,
        # marked as such, so each is pinned and cited like a member.
        inputs = [dict(p["ref"], cue_role=(p["payload"] or {}).get(
            "cue_role")) if (p["payload"] or {}).get("cue_role") else
            p["ref"] for p in left + right] + [b["ref"] for b in base_pins]
    from . import artifacts as artifactsmod
    key = artifactsmod.subject_key("drift", subject)
    eq = _carry_equivalence(host, key, eq)
    return {"left": left, "right": right, "L": L, "R": R,
            "left_refs": _drift_refs(left), "right_refs": _drift_refs(right),
            "labels": labels, "cue_equivalence": eq, "subject": subject,
            "subject_key": key,
            "n_cells": _n_cells(L + R, opts["contrast"]),
            "options": opts, "bases": bases,
            "baselines": _base_payloads(bases),
            "baseline_refs": _base_refs(bases),
            "inputs": inputs}


def _build_kw(prep):
    """The analysis choices and baselines as drift.build takes them --
    nothing at all for a default drift, so the call is today's call."""
    o = prep.get("options") or {}
    if drift.is_default(o):
        return {}
    kw = {"design": o["design"], "test": o["test"],
          "bh_scope": o["bh_scope"], "contrast": o["contrast"]}
    if o.get("contrast") == "baseline":
        kw["baselines"] = prep.get("baselines")
        kw["baseline_refs"] = prep.get("baseline_refs")
    return kw


def build_payload(prep, computed_on, progress=None):
    """drift.build on the prepared inputs. The same call the node makes."""
    return drift.build(prep["L"], prep["R"], prep["left_refs"],
                       prep["right_refs"], prep["labels"],
                       computed_on=computed_on,
                       cue_equivalence=prep["cue_equivalence"],
                       progress=progress, **_build_kw(prep))


# ==========================================================================
# Filing
# ==========================================================================
def file_drift(host, prep, payload, computed_on=None, nickname=None, by=None):
    """put, then cite every input version. The job's result."""
    arts = host.artifacts
    with _LOCK:
        before = arts.find("drift", prep["subject_key"])
        seen = {v.get("id") for v in ((before or {}).get("versions") or [])}
        params = dict(payload.get("params") or {},
                      test=(payload.get("test") or {}).get("name"),
                      cue_equivalence=[{"from": e["from"], "to": e["to"]}
                                       for e in prep["cue_equivalence"]])
        if not drift.is_default(prep.get("options")):
            o = prep["options"]
            params.update(design=o["design"], test=o["test"],
                          bh_scope=o["bh_scope"], contrast=o["contrast"])
        rec = arts.put("drift", prep["subject"], payload, params=params,
                       inputs=prep["inputs"], by=by, nickname=nickname)
        nick = (str(nickname).strip() if nickname else "") or None
        if before and nick and nick != rec.get("nickname"):
            rec = arts.set_nickname(rec["id"], nick, by=by)
        cur = max(rec.get("versions") or [{}],
                  key=lambda v: (v.get("v") or 0, v.get("at") or "",
                                 v.get("id") or ""))
        cited = []
        for ref in prep["inputs"]:
            arts.cite(ref["id"], ref["version_id"], rec["id"], cur["v"])
            cited.append({"id": ref["id"], "version": ref["version"],
                          "version_id": ref["version_id"]})
    new = cur.get("id") not in seen
    try:
        host.activity([{
            "action": "arc.drift.file",
            "detail": {"artifact": rec["id"], "version": cur.get("v"),
                       "new_version": new,
                       "left": len(prep["left"]), "right": len(prep["right"]),
                       "where": (computed_on or {}).get("kind")},
        }])
    except Exception:                                    # noqa: BLE001
        pass
    return {"ok": True, "artifact_id": rec["id"], "version": cur.get("v"),
            "version_id": cur.get("id"), "digest": cur.get("digest"),
            "name": rec.get("name"), "nickname": rec.get("nickname"),
            "new_version": new, "confirmed": not new, "cited": cited,
            "payload": payload,
            "computed_on": payload.get("computed_on")}


# ==========================================================================
# Running
# ==========================================================================
def _here(host):
    prov = _prov(host)
    return {"kind": "local", "machine": prov.get("machine"),
            "at": prov.get("at") or _now()}


def _spec(prep, where):
    return {"tool": "drift", "where": where, "left": len(prep["left"]),
            "right": len(prep["right"]), "cells": prep["n_cells"]}


def start_local(host, prep, nickname=None):
    def work(job):
        job.begin(STAGE, of=prep["n_cells"], unit="cells")
        on = _here(host)
        payload = build_payload(prep, on,
                                progress=lambda d, o: job.tick(STAGE, d))
        return file_drift(host, prep, payload, on, nickname)
    return cfc.start(_spec(prep, "local"), [(STAGE, prep["n_cells"])],
                     work, 1.0)


def _slim(payload):
    """A circuit payload without the per-pair values: `drift.pool` reads n,
    mean, sd and warn, never `values`, and the spec crosses ssh."""
    P = dict(payload)
    cells = {}
    for w, byw in (payload.get("cells") or {}).items():
        cells[w] = {}
        for m, panel in (byw or {}).items():
            cells[w][m] = {k: {x: v for x, v in c.items() if x != "values"}
                           for k, c in (panel or {}).items()}
    P["cells"] = cells
    return P


def node_spec(prep):
    kw = _build_kw(prep)
    # cue - baseline subtracts per cue pair, so it needs the `values` that
    # pooling alone never reads: those circuits travel whole.
    keep = kw.get("contrast") == "baseline"
    slim = (lambda p: p) if keep else _slim
    spec = {"path": None,
            "left": [slim(p) for p in prep["L"]],
            "right": [slim(p) for p in prep["R"]],
            "left_refs": prep["left_refs"], "right_refs": prep["right_refs"],
            "labels": prep["labels"],
            "cue_equivalence": prep["cue_equivalence"],
            "n_cells": prep["n_cells"]}
    if kw:
        spec["options"] = kw
    return spec


def run_node(spec, job):
    """What `vacc_run.py` calls for `tool == "drift"`: the same build."""
    job.begin(STAGE, of=spec.get("n_cells"), unit="cells")
    payload = drift.build(spec["left"], spec["right"], spec["left_refs"],
                          spec["right_refs"], spec["labels"],
                          computed_on={"kind": "vacc"},
                          cue_equivalence=spec.get("cue_equivalence"),
                          progress=lambda d, o: job.tick(STAGE, d),
                          **(spec.get("options") or {}))
    return {"schema": "arc.drift.node/1", "payload": payload}


def start_vacc(host, prep, nickname=None):
    st = {}
    try:
        st = host.vacc_status() or {}
    except Exception:                                    # noqa: BLE001
        st = {}
    can, why = vacc_ok(st)
    if not can:
        raise DriftRunError(why, 409)
    steps = [(STAGE, prep["n_cells"])]
    host.push_code()
    run = host.vacc_run(node_spec(prep),
                        max(60.0, prep["n_cells"] * cfc.rate_for(STAGE)),
                        steps)

    def work(job):
        out = run.work(job)
        body = (out or {}).get("payload")
        if not isinstance(body, dict) or body.get("schema") != drift.SCHEMA:
            raise DriftRunError("The cluster answered, but not with a "
                                "drift.", 502)
        cfg = getattr(run, "cfg", {}) or {}
        on = {"kind": "vacc", "host": cfg.get("host"),
              "netid": cfg.get("netid"), "slurm_id": run.slurm_id,
              "rid": run.rid, "partition": cfg.get("partition"),
              "at": _now()}
        body["computed_on"] = on
        return file_drift(host, prep, body, on, nickname)
    job = cfc.start(_spec(prep, "vacc"), _vacc_steps() + steps, work, 1.0,
                    "vacc:node")
    job.vacc_run = run
    return job


def _vacc_steps():
    from . import vaccrun
    return vaccrun.steps()
