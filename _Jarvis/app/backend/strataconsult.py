"""StrataScope Beta: Consult (2026-11-19).

The Beta tab of StrataScope has a Consult button. Pressing it "primes" a
consult: the labelling window sends what it is looking at -- the sheet, the
open step, the proposed lines where they are now, the depth curves, the
checks, and pictures of the traces, the depth strip and the evidence window
-- and this module keeps it on disk. Then the person comes to Claude Code
and says "consult". Claude reads it (tools/strata_consult.py show), writes a
reply -- notes, lines to move, channels to relabel, curves to look at,
parameters to change, each with its reason -- and pushes it
(tools/strata_consult.py push). The reply lands in the open window over
/api/link without a refresh, and the person applies it one item at a time.

Nothing here writes a label. A reply is a list of proposals; the page applies
the ones the person accepts through the same calls a hand edit makes, and
records what was applied, skipped or undone in decisions.json, so the next
consult knows.

Machine-local, under GUI_logs/.cache (gitignored): a consult is a
conversation with this computer's Claude, not lab data.

  POST /api/strata/<gid>/consult          prime one: {request, images}
  GET  /api/strata/<gid>/consult          the newest one: request head, reply, decisions
  POST /api/strata/<gid>/consult/reply    Claude's reply: {id?, reply}
  POST /api/strata/<gid>/consult/decide   {id, rev, index, state, detail}
  GET  /api/strata/consult/latest         the newest consult on any recording
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import re
import time

from flask import jsonify, request

ROOT = None                 # set by install(): GUI_logs/.cache/strata_consult
_A = None                   # the app module
LINK = "strata-consult:"    # + gid, on /api/link
IMG_NAMES = ("screen", "strip", "evidence", "rail")
MAX_IMG_BYTES = 12 * 1024 * 1024
KINDS = ("note", "move", "label", "confidence", "show", "step", "param")


def _is_test():
    try:
        return bool(_A and _A._request_is_test())
    except Exception:                                    # noqa: BLE001
        return False


def _safe(s):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s or ""))[:80] or "x"


def gid_dir(gid):
    return os.path.join(ROOT, _safe(gid))


def _write_json(path, obj):
    # temp + replace: a crash mid-write must not leave half a reply.
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def consults(gid):
    """This recording's consult ids, oldest first."""
    d = gid_dir(gid)
    if not os.path.isdir(d):
        return []
    return sorted(x for x in os.listdir(d)
                  if os.path.isfile(os.path.join(d, x, "request.json")))


def folder(gid, cid=None):
    ids = consults(gid)
    if cid is None:
        if not ids:
            return None
        cid = ids[-1]
    p = os.path.join(gid_dir(gid), _safe(cid))
    return p if os.path.isfile(os.path.join(p, "request.json")) else None


def save_request(gid, req, images):
    """Write one consult. Returns its id."""
    now = _dt.datetime.now()
    cid = now.strftime("%Y%m%d-%H%M%S")
    d = os.path.join(gid_dir(gid), cid)
    n = 1
    while os.path.exists(d):            # two presses in one second
        n += 1
        d = os.path.join(gid_dir(gid), "%s-%d" % (cid, n))
    cid = os.path.basename(d)
    os.makedirs(d, exist_ok=True)
    saved = []
    for name, url in (images or {}).items():
        if name not in IMG_NAMES or not isinstance(url, str):
            continue
        m = re.match(r"^data:image/(png|jpeg);base64,(.*)$", url, re.S)
        if not m:
            continue
        raw = base64.b64decode(m.group(2))
        if len(raw) > MAX_IMG_BYTES:
            continue
        ext = "png" if m.group(1) == "png" else "jpg"
        with open(os.path.join(d, name + "." + ext), "wb") as fh:
            fh.write(raw)
        saved.append(name + "." + ext)
    req = dict(req or {})
    req.update({"id": cid, "gid": gid, "at": now.isoformat(timespec="seconds"),
                "images": saved})
    # What was done with the replies to this recording's earlier consults,
    # so a reply can build on them rather than repeat itself.
    prev = consults(gid)
    prev = [x for x in prev if x != cid][-3:]
    req["earlier"] = [{"id": x,
                       "reply_summary": ((_read_json(os.path.join(
                           gid_dir(gid), x, "reply.json")) or {})
                           .get("summary")),
                       "decisions": _read_json(os.path.join(
                           gid_dir(gid), x, "decisions.json")) or {}}
                      for x in prev]
    _write_json(os.path.join(d, "request.json"), req)
    # A harness's consult (web/_dev/strataconsult.html) is kept but is never
    # "the newest": "consult" in Claude Code must not answer a test.
    if _is_test():
        return cid, d
    _write_json(os.path.join(ROOT, "LATEST.json"),
                {"gid": gid, "id": cid, "folder": d, "at": req["at"],
                 "label": req.get("label")})
    return cid, d


def public(gid, cid=None):
    """What the page needs: the request's head, the reply, the decisions."""
    d = folder(gid, cid)
    if not d:
        return None
    req = _read_json(os.path.join(d, "request.json")) or {}
    return {
        "id": os.path.basename(d),
        "at": req.get("at"),
        "note": req.get("note"),
        "step": req.get("open_step"),
        "images": req.get("images") or [],
        "reply": _read_json(os.path.join(d, "reply.json")),
        "decisions": _read_json(os.path.join(d, "decisions.json")) or {},
    }


def check_reply(reply):
    """Refuse a reply the page could not apply, with the reason."""
    if not isinstance(reply, dict):
        raise ValueError("A reply is a JSON object.")
    items = reply.get("items")
    if not isinstance(items, list):
        raise ValueError("A reply needs an items list (it may be empty).")
    for i, it in enumerate(items):
        k = (it or {}).get("kind")
        if k not in KINDS:
            raise ValueError("Item %d: kind must be one of %s, not %r."
                             % (i + 1, ", ".join(KINDS), k))
        if k == "move" and (it.get("to_ch") is None and it.get("to_row") is None):
            raise ValueError("Item %d: a move needs to_ch (the line goes "
                             "above that channel) or to_row." % (i + 1))
        if k == "move" and not (it.get("line") or (it.get("above") is not None
                                                   or it.get("below") is not None)):
            raise ValueError("Item %d: a move names its line: line (id) or "
                             "above/below (region ids)." % (i + 1))
        if k == "label" and (not isinstance(it.get("channels"), list)
                             or "region" not in it):
            raise ValueError("Item %d: a label needs channels (CSC numbers) "
                             "and region (an id, or null to clear)." % (i + 1))
        if k == "param" and "key" not in it:
            raise ValueError("Item %d: a param needs key and value." % (i + 1))
    return reply


def save_reply(gid, cid, reply):
    d = folder(gid, cid)
    if not d:
        raise ValueError("No consult to answer for %s." % gid)
    reply = check_reply(reply)
    old = _read_json(os.path.join(d, "reply.json")) or {}
    reply["rev"] = int(old.get("rev") or 0) + 1
    reply["at"] = _dt.datetime.now().isoformat(timespec="seconds")
    if old:
        hist = os.path.join(d, "replies")
        os.makedirs(hist, exist_ok=True)
        _write_json(os.path.join(hist, "rev%02d.json" % int(old.get("rev") or 0)),
                    old)
    _write_json(os.path.join(d, "reply.json"), reply)
    return os.path.basename(d), reply


def decide(gid, cid, rev, index, state, detail=None):
    d = folder(gid, cid)
    if not d:
        raise ValueError("No such consult.")
    path = os.path.join(d, "decisions.json")
    dec = _read_json(path) or {}
    dec["%s:%s" % (int(rev or 0), int(index))] = {
        "state": state, "at": _dt.datetime.now().isoformat(timespec="seconds"),
        "detail": detail}
    _write_json(path, dec)
    return dec


def install(app, A):
    global ROOT, _A
    _A = A
    ROOT = os.path.join(A.LOGS_DIR, ".cache", "strata_consult")
    os.makedirs(ROOT, exist_ok=True)

    def nudge(gid, cid, rev):
        try:
            A.live.publish(LINK + gid, {"at": time.time(), "id": cid,
                                        "rev": rev}, "claude")
        except Exception:                                # noqa: BLE001
            pass

    @app.route("/api/strata/<gid>/consult", methods=["GET", "POST"])
    def api_strata_consult(gid):
        if request.method == "GET":
            return jsonify({"ok": True, "consult": public(gid)})
        body = request.get_json(force=True) or {}
        try:
            cid, d = save_request(gid, body.get("request") or {},
                                  body.get("images") or {})
        except Exception as exc:                         # noqa: BLE001
            return A.fail("strata/consult", exc, 400, {"gid": gid})
        try:
            A.STORE.record_activity([{"action": "strata.consult",
                                      "detail": {"gid": gid, "id": cid}}])
        except Exception:                                # noqa: BLE001
            pass
        return jsonify({"ok": True, "id": cid, "folder": d,
                        "consult": public(gid, cid)})

    @app.route("/api/strata/<gid>/consult/reply", methods=["POST"])
    def api_strata_consult_reply(gid):
        body = request.get_json(force=True) or {}
        try:
            cid, reply = save_reply(gid, body.get("id"), body.get("reply"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:                         # noqa: BLE001
            return A.fail("strata/consult/reply", exc, 400, {"gid": gid})
        nudge(gid, cid, reply["rev"])
        return jsonify({"ok": True, "id": cid, "rev": reply["rev"],
                        "items": len(reply.get("items") or [])})

    @app.route("/api/strata/<gid>/consult/decide", methods=["POST"])
    def api_strata_consult_decide(gid):
        body = request.get_json(force=True) or {}
        try:
            dec = decide(gid, body.get("id"), body.get("rev"),
                         body.get("index"), str(body.get("state") or ""),
                         body.get("detail"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "decisions": dec})

    @app.route("/api/strata/consult/latest")
    def api_strata_consult_latest():
        last = _read_json(os.path.join(ROOT, "LATEST.json"))
        return jsonify({"ok": True, "latest": last})
