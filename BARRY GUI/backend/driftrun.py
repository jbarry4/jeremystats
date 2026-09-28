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
    on parameters; `drift.compatible` is still the test."""
    keep = {k: (params or {}).get(k) for k in drift.number_params(kind)}
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
            "current": row.get("id") == current_id}


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
                   "cue_label": r["cue_label"],
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
    }


def _pins(host, refs, side):
    got = [_pin(host, r, side) for r in (refs or [])]
    # Order does not change the answer: sorted by the pin itself.
    got.sort(key=lambda p: (p["ref"]["id"], p["ref"]["version_id"]))
    return got


def _drift_refs(pins):
    """What drift.build is handed as refs (and names members by)."""
    return [{"artifact_id": p["ref"]["id"], "version": p["ref"]["version"],
             "version_id": p["ref"]["version_id"],
             "digest": p["ref"]["digest"],
             "name": p["nickname"] or p["name"]} for p in pins]


def _n_cells(payloads):
    if not payloads:
        return 0
    first = payloads[0]
    n = len(first.get("region_order") or [])
    return (n * (n - 1) // 2 * len(first.get("windows") or [])
            * len(first.get("methods") or []))


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
    L = [p["payload"] for p in left]
    R = [p["payload"] for p in right]
    eq = body.get("cue_equivalence") or []
    try:
        eq = drift.clean_equivalence(eq)
    except drift.DriftError as exc:
        return {"compatible": False, "reasons": exc.reasons,
                "cue_only": False, "suggest": [], "cue_types": [],
                "warn": [], "cost": cost(host, len(L) + len(R), 0),
                "members": _members_out(left, right)}
    ok, reasons = drift.compatible(L, R, _drift_refs(left),
                                   _drift_refs(right), eq)
    cue_only, suggest = False, []
    if not ok and L and R:
        trial = _suggest(left, right)
        if trial:
            ok2, _r2 = drift.compatible(L, R, _drift_refs(left),
                                        _drift_refs(right), eq + trial)
            cue_only = ok2
            suggest = trial if ok2 else []
    warn = []
    for side, pins in (("left", left), ("right", right)):
        if len(pins) == 1:
            warn.append("The %s group is %s." % (side, drift.K1_SAY))
    return {"compatible": ok, "reasons": reasons, "cue_only": cue_only,
            "suggest": suggest, "cue_types": _cue_rows(left, right),
            "equivalence": eq, "warn": warn,
            "cost": cost(host, len(L) + len(R), _n_cells(L + R)),
            "members": _members_out(left, right)}


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
    L = [p["payload"] for p in left]
    R = [p["payload"] for p in right]
    prov = _prov(host)
    try:
        eq = drift.clean_equivalence(body.get("cue_equivalence") or [])
    except drift.DriftError as exc:
        raise DriftRunError(" ".join(exc.reasons), 400, reasons=exc.reasons)
    eq = [dict(e, by=e.get("by") or prov.get("user") or "not recorded",
               at=e.get("at") or _now()) for e in eq]
    ok, reasons = drift.compatible(L, R, _drift_refs(left),
                                   _drift_refs(right), eq)
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
    from . import artifacts as artifactsmod
    key = artifactsmod.subject_key("drift", subject)
    eq = _carry_equivalence(host, key, eq)
    return {"left": left, "right": right, "L": L, "R": R,
            "left_refs": _drift_refs(left), "right_refs": _drift_refs(right),
            "labels": labels, "cue_equivalence": eq, "subject": subject,
            "subject_key": key, "n_cells": _n_cells(L + R),
            "inputs": [p["ref"] for p in left] + [p["ref"] for p in right]}


def build_payload(prep, computed_on, progress=None):
    """drift.build on the prepared inputs. The same call the node makes."""
    return drift.build(prep["L"], prep["R"], prep["left_refs"],
                       prep["right_refs"], prep["labels"],
                       computed_on=computed_on,
                       cue_equivalence=prep["cue_equivalence"],
                       progress=progress)


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
    return {"path": None,
            "left": [_slim(p) for p in prep["L"]],
            "right": [_slim(p) for p in prep["R"]],
            "left_refs": prep["left_refs"], "right_refs": prep["right_refs"],
            "labels": prep["labels"],
            "cue_equivalence": prep["cue_equivalence"],
            "n_cells": prep["n_cells"]}


def run_node(spec, job):
    """What `vacc_run.py` calls for `tool == "drift"`: the same build."""
    job.begin(STAGE, of=spec.get("n_cells"), unit="cells")
    payload = drift.build(spec["left"], spec["right"], spec["left_refs"],
                          spec["right_refs"], spec["labels"],
                          computed_on={"kind": "vacc"},
                          cue_equivalence=spec.get("cue_equivalence"),
                          progress=lambda d, o: job.tick(STAGE, d))
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
