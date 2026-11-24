"""PROJECT EVOLVE phase 2's routes: branching labels out of a bank entry by
hand, and every thing's family (backend/family.py does the working out).

Kept out of app.py like er2routes.py: `install(app, A)` is called once with
the app module, whose BANK, ARTIFACTS, STORE and fail() are read off it when
a request needs them.

  GET  /api/family?entry=<id>              a bank entry's parents and children
  GET  /api/family?artifact=<id>&version=  an artifact's
  POST /api/bank/<id>/branch               {version, labels, name, note}
"""
from __future__ import annotations

from flask import jsonify, request

from . import family as familymod

BRANCH_PIPELINE = "Event Bank branch"


def _family(A):
    prefs = A.STORE.get_prefs() or {}
    folders = prefs.get(A.xraymanymod.FOLDERS_KEY) or {}
    rooms = A.ARTIFACTS.list(kind="extraction")
    wfs = A.ARTIFACTS.list(kind="rootcanal_workflow")
    defs = {}

    def defn_of(aid):
        if aid not in defs:
            try:
                pay = A.ARTIFACTS.payload(aid, None) or {}
            except Exception:                            # noqa: BLE001
                pay = {}
            defs[aid] = pay.get("definition") or {}
        return defs[aid]

    arts = {}

    def artifact(aid):
        if not aid:
            return None
        if aid not in arts:
            try:
                arts[aid] = A.ARTIFACTS.get(aid)
            except Exception:                            # noqa: BLE001
                arts[aid] = None
        return arts[aid]

    return familymod.Family(A.BANK.summaries(), artifact, folders, rooms,
                            wfs, defn_of)


def branch_shape(rec, labels):
    """(type, type_name, label map, words) of a branch of `rec` holding
    `labels`. A Root Canal bundle's single DS or P-spike label comes out as
    the plain entry its workflow would have banked (PROJECT EVOLVE phase 1),
    any other single label as itself, two or more as a bundle again. A
    Cell entry's branch is cells."""
    from . import rcworkflow
    names = rec.get("label_names") or {}
    t = rec.get("type") or "other"
    words = " + ".join(names.get(x, x) for x in labels)
    if t == "rcbundle":
        if len(labels) == 1 and labels[0] in rcworkflow.PLAIN:
            ptype, pname, plabel = rcworkflow.PLAIN[labels[0]]
            return ptype, pname, {labels[0]: plabel}, words
        if len(labels) == 1:
            return "other", names.get(labels[0], labels[0]), None, words
        return "rcbundle", rec.get("type_name") or "Root Canal bundle", \
            None, words
    return t, rec.get("type_name") or t, None, words


def branch_events(A, rec, version, labels):
    """The events of `rec` at `version` (its newest when None) in `labels`.

    The newest version's events are the entry's own and carry every field.
    An older one is rebuilt from its snapshot, which holds a time and a
    label; each is matched back to the entry's own event at that time and
    label for the rest (its recording, class, Halo). Returns (events,
    version row, dropped fields)."""
    vers = rec.get("versions") or []
    tip = vers[-1] if vers else None
    want = set(labels)
    if version in (None, "", "tip") or (tip and str(version) in (
            str(tip.get("id")), str(tip.get("v")))):
        evs = [dict(e) for e in rec.get("events") or []
               if (e.get("label_id") or e.get("label")) in want]
        return evs, tip, []
    snap, dropped = A.BANK.events_at(rec, version)
    ver = A.BANK.version_at(rec, version)
    full = {}
    for e in rec.get("events") or []:
        try:
            full[(round(float(e["start"]), 4),
                  e.get("label_id") or e.get("label"))] = e
        except (TypeError, ValueError, KeyError):
            continue
    out, missing = [], 0
    for e in snap:
        lid = e.get("label_id") or e.get("label")
        if lid not in want:
            continue
        hit = full.get((round(float(e["start"]), 4), lid))
        if hit:
            out.append(dict(hit))
        else:
            missing += 1
            out.append(dict(e))
    return out, ver, (dropped if missing else [])


def install(app, A):

    @app.route("/api/family")
    def api_family():
        eid = request.args.get("entry")
        aid = request.args.get("artifact")
        try:
            fam = _family(A)
            if eid:
                out = fam.of_entry(eid)
            elif aid:
                out = fam.of_artifact(aid, request.args.get("version"))
            else:
                return jsonify({"ok": False, "error": "Say which entry or "
                                "artifact (entry= or artifact=)."}), 400
        except KeyError as exc:
            return jsonify({"ok": False, "error": str(exc.args[0])}), 404
        except Exception as exc:                         # noqa: BLE001
            return A.fail("family", exc, 500, {"entry": eid,
                                               "artifact": aid})
        out["ok"] = True
        out["kinds"] = familymod.KIND_WORDS
        return jsonify(out)

    @app.route("/api/bank/<entry_id>/branch", methods=["POST"])
    def api_bank_branch(entry_id):
        """Split labels out of an entry into a new one that names its
        parent (PROJECT EVOLVE phase 2, 2026-11-21: "manual branch in the
        Event Bank"). The parent is never changed. Body: {version, labels,
        name, note, dry_run}."""
        body = request.get_json(force=True) or {}
        rec = A.BANK.get(entry_id)
        if not rec:
            return jsonify({"ok": False, "error": "No such entry."}), 404
        labels = [str(x) for x in (body.get("labels") or []) if x]
        names = rec.get("label_names") or {}
        try:
            if not labels:
                raise ValueError("Pick at least one label to branch out.")
            have = {(e.get("label_id") or e.get("label"))
                    for e in rec.get("events") or []}
            bad = [x for x in labels if x not in have and x not in names]
            if bad:
                raise ValueError("This entry has no label %s." % ", ".join(
                    "‘%s’" % b for b in bad))
            evs, ver, dropped = branch_events(A, rec, body.get("version"),
                                              labels)
            if not evs:
                raise ValueError("None of its events at that version carry "
                                 "those labels.")
            ptype, pname, relabel, words = branch_shape(rec, labels)
            if relabel:
                for e in evs:
                    lid = e.get("label_id") or e.get("label")
                    if lid in relabel:
                        e.update(relabel[lid])
            vlabel = None
            if ver:
                vlabel = "v%s" % (ver.get("label") or ver.get("v"))
            counts = {}
            for e in evs:
                k = e.get("label_id") or e.get("label")
                counts[k] = counts.get(k, 0) + 1
            if body.get("dry_run"):
                return jsonify({"ok": True, "dry_run": True, "n": len(evs),
                                "type": ptype, "type_name": pname,
                                "counts": counts, "dropped": dropped,
                                "version": vlabel})
            who = (A.STORE.provenance() or {}).get("user")
            parent = {"entry_id": rec["id"], "name": rec.get("name"),
                      "version": (ver or {}).get("id") or (ver or {}).get("v"),
                      "version_label": vlabel,
                      "labels": [{"id": x, "label": names.get(x, x)}
                                 for x in labels]}
            keep_names = ({x: names[x] for x in labels if x in names}
                          if not relabel else None)
            made = A.BANK.add({
                "project": rec.get("project"), "mouse": rec.get("mouse"),
                "session": rec.get("session"),
                "session_key": rec.get("session_key"),
                "session_loose_key": rec.get("session_loose_key"),
                "session_label": rec.get("session_label"),
                "session_path": rec.get("session_path"),
                "recording_start": rec.get("recording_start"),
                "duration_s": rec.get("duration_s"), "gid": rec.get("gid"),
                "type": ptype, "type_name": pname,
                "label_names": keep_names,
                "name": (str(body.get("name") or "").strip()
                         or "%s · from %s" % (words, rec.get("name"))),
                "note": ("Branched by hand from ‘%s’ %s: the %s events "
                         "labeled %s. The parent is unchanged."
                         % (rec.get("name"), vlabel or "", len(evs), words)
                         ).replace("  ", " ")
                        + ((" " + str(body.get("note")).strip())
                           if str(body.get("note") or "").strip() else ""),
                "events": evs,
                "curated": bool(rec.get("specified")),
                "pipeline": BRANCH_PIPELINE,
                "added_by": who,
                "aligned": rec.get("aligned"),
                "time_basis": rec.get("time_basis"),
                "parent": parent,
                "parameters": {"tool": "bank_branch", "parent": parent,
                               "from_type": rec.get("type"),
                               "parent_parameters": {
                                   k: v for k, v in ((rec.get("source") or {})
                                                     .get("parameters") or {})
                                   .items() if k != "sources"}},
            })
        except A.eventbank.BankError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:                         # noqa: BLE001
            return A.fail("bank/branch", exc, 400, {"entry": entry_id})
        A.STORE.record_activity([{"action": "bank.branch", "detail": {
            "id": made.get("id"), "parent": entry_id, "labels": labels,
            "n": made.get("n"), "type": ptype}}])
        A.mirror_bank_soon()
        return jsonify({"ok": True, "entry_id": made["id"],
                        "name": made.get("name"), "n": made.get("n"),
                        "type": ptype, "counts": counts,
                        "dropped": dropped})
