"""Sextant's routes (Seahorse's review and Accept; StrataScope's proposal).

`install(app, A)` is called once with the app module (LAYERS, STORE,
PROFILE, LOGS_DIR and APP_DIR are read off it when a request needs them).

  POST /api/sextant/<gid>/refit      a dragged probe: the best fit near it
  POST /api/sextant/<gid>/accept     keep a placement (on the layer sheet,
                                     field strata_sextant, synced like the
                                     rest of the sheet's StrataScope fields)
  POST /api/sextant/<gid>/accepted   the kept placement, if any
  POST /api/sextant/<gid>/proposal   the layers StrataScope should hatch:
                                     the kept placement's, else Sextant's own
  POST /api/sextant/<gid>/to_strata  StrataScope's Accept: write them as labels
"""
from __future__ import annotations

import json
import os

from flask import jsonify, request

from .. import shards
from . import refit as RF
from . import report as REP


def _web(A):
    return os.path.join(A.APP_DIR, "web", "seahorse", "sextant")


def _answer(A, gid):
    p = os.path.join(_web(A), gid + ".json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _strata_of(layers):
    return [REP.TO_STRATA.get(k) if k else None for k in layers]


def _proposal(A, gid):
    rec = A.LAYERS.get(gid) or {}
    acc = rec.get("strata_sextant") or None
    if acc and acc.get("strata"):
        return {"from": "accepted", "strata": acc["strata"], "line": acc.get("line"), "at": acc.get("at"),
                "by": acc.get("by")}
    rep = _answer(A, gid)
    if rep:
        return {"from": "sextant", "strata": rep["answer"]["strata"], "line": rep["answer"]["line"],
                "words": rep["answer"]["words"]}
    return None


def install(app, A):

    @app.route("/api/sextant/<gid>/refit", methods=["POST"])
    def api_sextant_refit(gid):
        body = request.get_json(force=True) or {}
        line = body.get("line")
        try:
            if not (isinstance(line, list) and len(line) == 2 and all(len(p) == 3 for p in line)):
                raise ValueError("A line is two points of three numbers (contact 1, contact 64; CCF um).")
            out = RF.local(A.LOGS_DIR, _web(A), gid, [[float(x) for x in p] for p in line])
        except Exception as exc:                          # noqa: BLE001
            return A.fail("sextant/refit", exc, 400, {"gid": gid})
        return jsonify(out)

    @app.route("/api/sextant/<gid>/accept", methods=["POST"])
    def api_sextant_accept(gid):
        body = request.get_json(force=True) or {}
        line, layers = body.get("line"), body.get("layers") or []
        try:
            if not (isinstance(line, list) and len(line) == 2):
                raise ValueError("Which line?")
            if len(layers) != 64:
                raise ValueError("The layers under all 64 contacts are needed.")
            if not A.LAYERS.get(gid):
                A.LAYERS.ensure(gid, channels=list(range(1, 65)))
            who = (A.PROFILE.effective() or {}).get("user")
            acc = {"line": [[round(float(x), 1) for x in p] for p in line], "layers": layers,
                   "strata": _strata_of(layers), "source": body.get("source") or "sextant",
                   "by": who, "at": shards._now()}
            A.LAYERS.set_strata(gid, {"sextant": acc})
        except Exception as exc:                          # noqa: BLE001
            return A.fail("sextant/accept", exc, 400, {"gid": gid})
        A.STORE.record_activity([{"action": "sextant.accept", "detail": {"gid": gid, "source": acc["source"]}}])
        return jsonify({"ok": True, "accepted": acc})

    @app.route("/api/sextant/<gid>/accepted", methods=["POST"])
    def api_sextant_accepted(gid):
        rec = A.LAYERS.get(gid) or {}
        return jsonify({"ok": True, "accepted": rec.get("strata_sextant") or None})

    @app.route("/api/sextant/<gid>/proposal", methods=["POST"])
    def api_sextant_proposal(gid):
        return jsonify({"ok": True, "proposal": _proposal(A, gid)})

    @app.route("/api/sextant/<gid>/to_strata", methods=["POST"])
    def api_sextant_to_strata(gid):
        """StrataScope's Accept: Sextant's layers become the sheet's labels,
        channel k = contact k (the H3 in the recording's own order), only on
        the channels the sheet has; a contact with no StrataScope name (CA2,
        CA3) is left as it is."""
        prop = _proposal(A, gid)
        try:
            if not prop:
                raise ValueError("Sextant has not placed this recording.")
            rec = A.LAYERS.get(gid) or {}
            chans = {int(c) for c in (rec.get("channels") or range(1, 65))}
            labels = {str(k + 1): r for k, r in enumerate(prop["strata"]) if r and (k + 1) in chans}
            out = A.LAYERS.apply_step(gid, labels, {})
        except Exception as exc:                          # noqa: BLE001
            return A.fail("sextant/to_strata", exc, 400, {"gid": gid})
        A.STORE.record_activity([{"action": "sextant.to_strata", "detail": {"gid": gid, "labels": len(labels),
                                                                           "from": prop["from"]}}])
        return jsonify({"ok": True, "sheet": A.LAYERS.summary(out), "n": len(labels)})
