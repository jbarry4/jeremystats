# -*- coding: utf-8 -*-
"""Seahorse (the mouse-brain atlas tab): what the lab adds to it.

Everything the atlas itself shows is built offline into web/seahorse/ by
tools/seahorse/. What people add while using it lives here, in
GUI_logs/seahorse/ shards, so it travels between lab machines the way the
rest of GUI_logs does:

  lab@<machine>.json
    notes   {id: {target: {type, key}, text, by, at}}    lab notes on any
                                                          structure, cell,
                                                          connection or layer
    views   {id: {name, state, by, at}}                   saved views (camera,
                                                          cut, selection),
                                                          shareable by id
  quiz@<machine>.json
    cards   {"<person>|<card id>": {due, ivl, ease, reps, lapses, last}}
                                                          spaced-repetition
                                                          state, per person

Each field is a per-id map merged last-write-wins across machines
(shards.MAPLWW), so two people adding notes on two computers both keep
theirs, and a deletion (a None) travels.
"""
import re
import threading
import time
import uuid

from flask import jsonify, request

from . import shards

SPEC = {"notes": shards.MAPLWW, "views": shards.MAPLWW, "cards": shards.MAPLWW}
_LOCK = threading.Lock()
MAX_TEXT = 4000
MAX_STATE = 20000


class SeahorseLab:
    def __init__(self, logs_dir, store=None):
        import os
        self.book = shards.Book(os.path.join(logs_dir, "seahorse"), SPEC, store)

    def _read(self, base):
        rec = self.book.read(base) or {}
        for f in ("notes", "views", "cards"):
            rec.setdefault(f, {})
        return rec

    def lab(self):
        rec = self._read("lab")
        return {"notes": rec["notes"], "views": rec["views"]}

    def put(self, field, item_id, value):
        with _LOCK:
            rec = self._read("lab")
            if value is None:
                rec[field].pop(item_id, None)
            else:
                rec[field][item_id] = value
            self.book.write("lab", rec)
        return self.lab()

    def quiz(self, person):
        rec = self._read("quiz")
        pre = (person or "") + "|"
        return {k[len(pre):]: v for k, v in rec["cards"].items() if k.startswith(pre) and v}

    def put_card(self, person, card, state):
        with _LOCK:
            rec = self._read("quiz")
            rec["cards"][(person or "") + "|" + card] = state
            self.book.write("quiz", rec)
        return self.quiz(person)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _clean_id(s):
    s = str(s or "")
    return s if re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", s) else None


def install(app, fail, logs_dir, store=None, who=None):
    LAB = SeahorseLab(logs_dir, store)
    me = who or (lambda: "")

    @app.route("/api/seahorse/lab")
    def api_seahorse_lab():
        try:
            return jsonify({"ok": True, "me": me() or "", **LAB.lab()})
        except Exception as e:                           # noqa: BLE001
            return fail("seahorse lab", e)

    @app.route("/api/seahorse/note", methods=["POST"])
    def api_seahorse_note():
        """{id?, target: {type, key}, text} adds or edits a note;
        {id, delete: true} removes it."""
        b = request.get_json(force=True) or {}
        try:
            nid = _clean_id(b.get("id")) or ("n" + uuid.uuid4().hex[:10])
            if b.get("delete"):
                return jsonify({"ok": True, **LAB.put("notes", nid, None)})
            tgt = b.get("target") or {}
            text = str(b.get("text") or "").strip()[:MAX_TEXT]
            if not text or not tgt.get("type") or not tgt.get("key"):
                return jsonify({"ok": False, "error": "A note needs some text and a target."}), 400
            val = {"target": {"type": str(tgt["type"])[:20], "key": str(tgt["key"])[:60]},
                   "text": text, "by": me() or "", "at": _now()}
            return jsonify({"ok": True, "id": nid, **LAB.put("notes", nid, val)})
        except Exception as e:                           # noqa: BLE001
            return fail("seahorse note", e)

    @app.route("/api/seahorse/view", methods=["POST"])
    def api_seahorse_view():
        """{id?, name, state} saves a view; {id, delete: true} removes it."""
        b = request.get_json(force=True) or {}
        try:
            vid = _clean_id(b.get("id")) or ("v" + uuid.uuid4().hex[:8])
            if b.get("delete"):
                return jsonify({"ok": True, **LAB.put("views", vid, None)})
            import json as _json
            state = b.get("state") or {}
            if len(_json.dumps(state)) > MAX_STATE:
                return jsonify({"ok": False, "error": "That view is too big to save."}), 400
            name = str(b.get("name") or "").strip()[:80] or "Untitled view"
            val = {"name": name, "state": state, "by": me() or "", "at": _now()}
            return jsonify({"ok": True, "id": vid, **LAB.put("views", vid, val)})
        except Exception as e:                           # noqa: BLE001
            return fail("seahorse view", e)

    @app.route("/api/seahorse/quiz", methods=["GET", "POST"])
    def api_seahorse_quiz():
        try:
            person = me() or ""
            if request.method == "GET":
                return jsonify({"ok": True, "me": person, "cards": LAB.quiz(person)})
            b = request.get_json(force=True) or {}
            card = _clean_id(b.get("card"))
            st = b.get("state") or {}
            if not card:
                return jsonify({"ok": False, "error": "Which card?"}), 400
            keep = {k: st[k] for k in ("due", "ivl", "ease", "reps", "lapses", "last") if k in st}
            return jsonify({"ok": True, "me": person, "cards": LAB.put_card(person, card, keep)})
        except Exception as e:                           # noqa: BLE001
            return fail("seahorse quiz", e)

    return LAB
