"""The Cells' routes (PROJECT EVOLVE phase 7, 2026-11-21). backend/cells.py
does the reading and the arithmetic; this finds the recordings, keeps the
curation versions (artifact kind `cell_curation`) and banks.

  GET  /api/cells/sorts                 every recording here with a sort
  GET  /api/cells/<gid>                 its run, sources, versions, cells
  POST /api/cells/<gid>/read            {source}: read a source -> a version
  GET  /api/cells/<gid>/diff?a=&b=      two versions compared cell by cell
  GET  /api/cells/<gid>/cell/<id>       one cell closely (?version=&invert=)
  GET  /api/cells/<gid>/window          spikes in [t0, t1] (?version=)
  GET  /api/cells/<gid>/bundles         bank sets with events here, by label
  POST /api/cells/<gid>/peth            {version, entry_id, labels, cells}
  POST /api/cells/<gid>/bank            {version, name, note}
"""
from __future__ import annotations

import os
import threading
import time

import numpy as np
from flask import jsonify, request

from . import cells as C

KIND = "cell_curation"
PIPELINE = "Kilosort 4 · curated cells"
_SORTS = {"at": 0.0, "rows": None}
_LOCK = threading.Lock()
_TTL = 120.0


def install(app, A):

    cache_dir = os.path.join(A.LOGS_DIR, ".cache", "cells")

    # ------------------------------------------------------------------
    # Finding things
    # ------------------------------------------------------------------
    def reg_row(gid):
        row = A._session_by_gid(gid)
        if not row:
            raise ValueError("There is no recording %s." % gid)
        return row

    def path_of(row):
        here = row.get("here") or []
        if here:
            return here[0]
        p = A._local_path_of(row)
        if p:
            return p
        raise ValueError("%s is not on this computer, so its sort cannot be "
                         "read here." % (row.get("label") or row.get("gid")))

    def curation_of(gid, run_name):
        return A.ARTIFACTS.find(KIND, {"gid": gid, "run": run_name})

    def entry_of(gid, run_dir):
        """The Cell entry already banked for this recording's sort."""
        hit = None
        for r in A.BANK.summaries():
            prm = ((r.get("source") or {}).get("parameters") or {})
            if r.get("type") == "cell" and prm.get("tool") == "cells" and \
                    r.get("gid") == gid and prm.get("run_dir") == run_dir:
                hit = r
        return hit

    def sheet_of(gid):
        """The recording's layer sheet, with the whole vocabulary's names
        and colours (layers.regions_for), or None."""
        try:
            rec = A.LAYERS.get(gid)
            if rec and rec.get("labels"):
                return dict(rec, regions=A.layers.regions_for(rec))
            return rec
        except Exception:                                # noqa: BLE001
            return None

    def report_of(path):
        rep = A.continuitymod.check(path)
        if not rep or not rep.get("breaks"):
            raise ValueError("Jarvis could not map this recording's samples "
                             "to its own seconds (no continuity map), so "
                             "spike times cannot be placed.")
        return rep

    def version_payload(aid, version):
        pay = A.ARTIFACTS.payload(aid, version)
        if pay is None:
            raise ValueError("That curation version was read on another "
                             "computer and has not reached this one.")
        return pay

    def spikes_for(gid, path, run, pay):
        """({id: samples}, {id: seconds}) for a version: from the cache,
        else read again from its source -- refused when the source has
        moved on since (its cells no longer match the version's)."""
        want = {int(c["id"]): c.get("digest") for c in pay.get("cells") or []}
        dig = pay.get("source_digest")
        p = C.cache_path(cache_dir, gid, run["name"], dig or "x")
        cells, secs = C.load_cells(p)
        if cells is not None:
            return cells, secs
        src = (pay.get("source") or {}).get("kind")
        cells = C.read_source(path, run["path"], src)
        got = {c: C._digest(s) for c, s in cells.items()}
        if got != want:
            raise ValueError("Its source (%s) has changed since this version "
                             "was read, and this computer kept no copy of "
                             "the spikes it held. Read the source again for "
                             "a new version." % (pay.get("source") or {})
                             .get("name"))
        rep = report_of(path)
        secs = {c: C.true_seconds(rep, s) for c, s in cells.items()}
        C.save_cells(p, cells, secs)
        return cells, secs

    def resolve(gid, version=None):
        row = reg_row(gid)
        path = path_of(row)
        run, twin = C.pick_run(path)
        if not run:
            raise ValueError("%s has no Kilosort sort beside it." % (
                row.get("label") or gid))
        art = curation_of(gid, run["name"])
        return row, path, run, twin, art

    # ------------------------------------------------------------------
    # The list
    # ------------------------------------------------------------------
    def scan():
        rows = []
        bank = {}
        for r in A.BANK.summaries():
            prm = ((r.get("source") or {}).get("parameters") or {})
            if r.get("type") == "cell" and prm.get("tool") == "cells":
                bank.setdefault(r.get("gid"), r)
        curs = {(a.get("subject") or {}).get("gid"): a
                for a in A.ARTIFACTS.list(kind=KIND)}
        seen = set()
        for rec in A.REG.all() or []:
            gid = rec.get("gid")
            if not gid or gid in seen:
                continue
            seen.add(gid)
            path = A._local_path_of(rec)
            if not path or not os.path.isdir(C.binary_dir(path)):
                continue
            run, twin = C.pick_run(path)
            if not run:
                continue
            ex = C.export_dir(path)
            ph = C.phy_state(run["path"])
            cur = curs.get(gid)
            ent = bank.get(gid)
            rows.append({
                "gid": gid, "label": rec.get("label"),
                "project": rec.get("project"), "mouse": rec.get("mouse"),
                "session": rec.get("session"), "path": path,
                "run": run["name"], "run_dir": run["path"],
                "twin": twin["name"] if twin else None,
                "binary": os.path.isfile(os.path.join(C.binary_dir(path),
                                                      "CSC_Raw.dat")),
                "export_n": (len([n for n in C._ls(ex)
                                  if n.lower().endswith(".mat")])
                             if ex else 0),
                "phy_edited": ph["edited"], "phy_at": ph["at"],
                "curation": ({"artifact_id": cur["id"],
                              "version": cur.get("version"),
                              "cells": ((cur.get("current") or {})
                                        .get("n_summary") or {}).get("cells")}
                             if cur else None),
                "entry": ({"id": ent["id"], "name": ent.get("name"),
                           "n": ent.get("n")} if ent else None),
            })
        rows.sort(key=lambda r: (str(r.get("project") or ""),
                                 A.natsortmod.key(r.get("label") or r["gid"])))
        return rows

    @app.route("/api/cells/sorts")
    def api_cells_sorts():
        force = request.args.get("force") == "1"
        try:
            with _LOCK:
                if force or _SORTS["rows"] is None or \
                        time.time() - _SORTS["at"] > _TTL:
                    _SORTS["rows"] = scan()
                    _SORTS["at"] = time.time()
                rows = _SORTS["rows"]
        except Exception as exc:                         # noqa: BLE001
            return A.fail("cells/sorts", exc, 500)
        return jsonify({"ok": True, "sorts": rows,
                        "curated": sum(1 for r in rows if r["export_n"]),
                        "n": len(rows)})

    def drop_scan():
        _SORTS["rows"] = None

    # ------------------------------------------------------------------
    # One recording
    # ------------------------------------------------------------------
    @app.route("/api/cells/<gid>")
    def api_cells_one(gid):
        ver = request.args.get("version")
        try:
            row, path, run, twin, art = resolve(gid)
            desc = C.describe(path)
            out = {"ok": True, "gid": gid, "label": row.get("label"),
                   "path": path, "run": run, "twin": twin,
                   "binary": desc["binary"], "sources": desc["sources"],
                   "curation": None, "cells": [], "version": None}
            if art:
                rec = A.ARTIFACTS.get(art["id"])
                vs = []
                for v in rec.get("versions") or []:
                    ns = v.get("n_summary") or {}
                    vs.append({"v": v.get("v"), "id": v.get("id"),
                               "at": v.get("at"), "by": v.get("by"),
                               "note": v.get("note"),
                               "n": ns.get("cells"),
                               "source": ns.get("source_name"),
                               "here": v.get("here", True),
                               "confirmed": v.get("confirmed")})
                want = int(ver) if ver else rec.get("version")
                pay = A.ARTIFACTS.payload(art["id"], want)
                out["curation"] = {"artifact_id": art["id"],
                                   "version": rec.get("version"),
                                   "versions": vs}
                out["version"] = want
                if pay:
                    out["cells"] = pay.get("cells") or []
                    out["source"] = pay.get("source")
                    out["polarity"] = pay.get("polarity")
            ent = entry_of(gid, run["path"])
            out["entry"] = ({"id": ent["id"], "name": ent.get("name"),
                             "n": ent.get("n"),
                             "version": (((ent.get("source") or {})
                                          .get("parameters") or {})
                                         .get("curation") or {})
                             .get("version")} if ent else None)
        except Exception as exc:                         # noqa: BLE001
            return A.fail("cells/one", exc, 400, {"gid": gid})
        return jsonify(C.jsonsafe(out))

    @app.route("/api/cells/<gid>/read", methods=["POST"])
    def api_cells_read(gid):
        """Read one source into a curation version. The same cells read
        again confirm the version rather than mint another."""
        body = request.get_json(force=True) or {}
        kind = body.get("source") or "export"
        try:
            row, path, run, twin, art = resolve(gid)
            src = next((s for s in C.sources(path, run["path"])
                        if s["kind"] == kind), None)
            if not src:
                raise ValueError("This recording has no %s to read." % (
                    "export" if kind == "export" else "Phy curation"))
            cells = C.read_source(path, run["path"], kind)
            if not cells:
                raise ValueError("%s holds no cells." % src["name"])
            exact = C.check_against_run(run["path"], cells)
            rep = report_of(path)
            secs = {c: C.true_seconds(rep, s) for c, s in cells.items()}
            dig = C.source_digest(cells)
            C.save_cells(C.cache_path(cache_dir, gid, run["name"], dig),
                         cells, secs)
            rows = C.cell_table(run["path"], cells, rep, sheet_of(gid))
            pol = raw_polarity(path, run["path"], cells, rows)
            pay = C.payload_for(src, run, rows, row.get("label"), pol)
            pay["source_digest"] = dig
            pay["exact_clusters"] = exact
            pay["layers_from"] = ("the layer sheet (%s)" % (
                ((sheet_of(gid) or {}).get("versions") or [{}])[-1]
                .get("by") or "StrataScope")) if sheet_of(gid) else None
            saved = A.ARTIFACTS.put(
                KIND, {"gid": gid, "run": run["name"],
                       "run_dir": run["path"],
                       "session_label": row.get("label")},
                C.jsonsafe(pay),
                params={"source": kind},
                note=body.get("note") or "Read from %s (%s)." % (
                    src["name"], src.get("at") or "undated"))
        except Exception as exc:                         # noqa: BLE001
            return A.fail("cells/read", exc, 400, {"gid": gid,
                                                   "source": kind})
        drop_scan()
        A.STORE.record_activity([{"action": "cells.read", "detail": {
            "gid": gid, "source": kind, "cells": len(rows),
            "artifact": saved["id"], "version": saved.get("version")}}])
        return jsonify({"ok": True, "artifact_id": saved["id"],
                        "version": saved.get("version"), "cells": len(rows),
                        "exact": exact, "polarity": pol})

    def raw_polarity(path, run_dir, cells, rows):
        """The polarity check: each cell's mean of 100 spikes on its best
        contact, in the binary's own sign, read against the header's
        InputInverted (the signals' Invert toggle, for the sort)."""
        raw = os.path.join(C.binary_dir(path), "CSC_Raw.dat")
        if not os.path.isfile(raw):
            return None
        inv = None
        try:
            hdr = A.nlx.read_header(os.path.join(
                path, "CSC%d.ncs" % rows[0]["csc"]))
            got = str(hdr.get("InputInverted") or "").strip().lower()
            inv = True if got == "true" else False if got == "false" else None
        except Exception:                                # noqa: BLE001
            inv = None
        waves = []
        for r in rows:
            w = C.waveform(raw, run_dir, cells[int(r["id"])], r["ch_index"],
                           1.0, 1.0, n=100)
            waves.append({"down": bool(w and w.get("down"))} if w else None)
            r["binary_down"] = bool(w and w.get("down")) if w else None
        return C.polarity(waves, inv)

    @app.route("/api/cells/<gid>/diff")
    def api_cells_diff(gid):
        a, b = request.args.get("a"), request.args.get("b")
        try:
            row, path, run, twin, art = resolve(gid)
            if not art:
                raise ValueError("Nothing has been read for this recording.")
            pa = version_payload(art["id"], int(a))
            pb = version_payload(art["id"], int(b))
            ca, _ = spikes_for(gid, path, run, pa)
            cb, _ = spikes_for(gid, path, run, pb)
            got = C.diff(ca, cb)
        except Exception as exc:                         # noqa: BLE001
            return A.fail("cells/diff", exc, 400, {"gid": gid})
        got.update(ok=True, a=int(a), b=int(b),
                   a_source=(pa.get("source") or {}).get("name"),
                   b_source=(pb.get("source") or {}).get("name"))
        return jsonify(C.jsonsafe(got))

    def _pick_version(art, ver):
        if not art:
            raise ValueError("Nothing has been read for this recording yet.")
        return int(ver) if ver else int(art.get("version") or 1)

    @app.route("/api/cells/<gid>/cell/<int:cid>")
    def api_cells_cell(gid, cid):
        ver = request.args.get("version")
        invert = request.args.get("invert", "1") != "0"
        try:
            row, path, run, twin, art = resolve(gid)
            v = _pick_version(art, ver)
            pay = version_payload(art["id"], v)
            cells, secs = spikes_for(gid, path, run, pay)
            if cid not in cells:
                raise ValueError("Cell %d is not in v%d." % (cid, v))
            info = next(c for c in pay["cells"] if int(c["id"]) == cid)
            s, t = cells[cid], secs[cid]
            raw = os.path.join(C.binary_dir(path), "CSC_Raw.dat")
            uv = 1.0
            try:
                hdr = A.nlx.read_header(os.path.join(
                    path, "CSC%d.ncs" % info["csc"]))
                uv = (A.nlx._header_float(hdr, "ADBitVolts")
                      or A.nlx.FALLBACK_ADBITVOLTS) * 1e6
            except Exception:                            # noqa: BLE001
                uv = A.nlx.FALLBACK_ADBITVOLTS * 1e6
            rep = report_of(path)
            dur = float(C.true_seconds(rep, [int(rep["total_samples"]) - 1])[0])
            out = {"ok": True, "gid": gid, "version": v, "cell": info,
                   "isi": C.isi(s), "acg": C.acg(s),
                   "rate": C.rate(t, dur),
                   "amplitude": C.amplitudes(run["path"], s, t),
                   "waveform": (C.waveform(raw, run["path"], s,
                                           info["ch_index"], uv,
                                           -1.0 if invert else 1.0)
                                if os.path.isfile(raw) else None),
                   "invert": invert, "duration_s": dur}
        except Exception as exc:                         # noqa: BLE001
            return A.fail("cells/cell", exc, 400, {"gid": gid, "cell": cid})
        return jsonify(C.jsonsafe(out))

    @app.route("/api/cells/<gid>/window")
    def api_cells_window(gid):
        ver = request.args.get("version")
        try:
            t0 = float(request.args.get("t0") or 0)
            t1 = float(request.args.get("t1") or 0)
            row, path, run, twin, art = resolve(gid)
            v = _pick_version(art, ver)
            pay = version_payload(art["id"], v)
            cells, secs = spikes_for(gid, path, run, pay)
            out = []
            for c in pay["cells"]:
                t = secs.get(int(c["id"]))
                if t is None:
                    continue
                a = np.searchsorted(t, t0)
                b = np.searchsorted(t, t1, side="right")
                got = t[a:b]
                if len(got) > 4000:
                    got = got[:: int(np.ceil(len(got) / 4000))]
                out.append({"id": c["id"], "csc": c["csc"],
                            "layer": c.get("layer"),
                            "layer_name": c.get("layer_name"),
                            "layer_color": c.get("layer_color"),
                            "depth_um": c.get("depth_um"),
                            "t": np.round(got, 5).tolist(),
                            "n": int(b - a)})
        except Exception as exc:                         # noqa: BLE001
            return A.fail("cells/window", exc, 400, {"gid": gid})
        return jsonify({"ok": True, "version": v, "t0": t0, "t1": t1,
                        "cells": out})

    def label_events(gid, entry_id, labels):
        rec = A.BANK.get(entry_id)
        if not rec:
            raise ValueError("No such bank entry.")
        names = rec.get("label_names") or {}
        by = {}
        for e in rec.get("events") or []:
            g = e.get("gid") or rec.get("gid")
            if g != gid:
                continue
            lid = e.get("label_id") or e.get("label") or "unlabeled"
            if labels and lid not in labels:
                continue
            by.setdefault(lid, []).append(float(e["start"]))
        return rec, {k: sorted(v) for k, v in by.items()}, names

    @app.route("/api/cells/<gid>/bundles")
    def api_cells_bundles(gid):
        """Bank sets with events on this recording, newest first, with how
        many each label holds -- what firing can be lined up on."""
        out = []
        try:
            for r in A.BANK.summaries():
                if r.get("archived") or r.get("type") == "cell":
                    continue
                prm = ((r.get("source") or {}).get("parameters") or {})
                mine = r.get("gid") == gid
                srcs = prm.get("sources") or []
                pooled = any(s.get("gid") == gid for s in srcs)
                if not (mine or pooled):
                    continue
                out.append({"id": r["id"], "name": r.get("name"),
                            "type": r.get("type"),
                            "type_name": r.get("type_name"),
                            "bundle": r.get("type") == "rcbundle",
                            "at": (r.get("added") or {}).get("at"),
                            "labels": [{"id": lab.get("id"),
                                        "label": lab.get("label")}
                                       for lab in prm.get("labels") or []]
                            or [{"id": k, "label": v} for k, v in
                                (r.get("label_names") or {}).items()]})
            # Bundles first, newest first among each.
            out.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
            out.sort(key=lambda r: (0 if r["bundle"] else 1))
        except Exception as exc:                         # noqa: BLE001
            return A.fail("cells/bundles", exc, 400, {"gid": gid})
        return jsonify({"ok": True, "sets": out})

    @app.route("/api/cells/<gid>/peth", methods=["POST"])
    def api_cells_peth(gid):
        body = request.get_json(force=True) or {}
        try:
            row, path, run, twin, art = resolve(gid)
            v = _pick_version(art, body.get("version"))
            pay = version_payload(art["id"], v)
            cells, secs = spikes_for(gid, path, run, pay)
            rec, by, names = label_events(gid, body.get("entry_id"),
                                          body.get("labels"))
            want = [int(c) for c in (body.get("cells") or [])] or \
                sorted(cells)
            out = {}
            for cid in want:
                if cid not in secs:
                    continue
                out[str(cid)] = {lid: C.peth(secs[cid], ev)
                                 for lid, ev in by.items()}
        except Exception as exc:                         # noqa: BLE001
            return A.fail("cells/peth", exc, 400, {"gid": gid})
        return jsonify(C.jsonsafe({
            "ok": True, "version": v, "entry": {"id": rec["id"],
                                                "name": rec.get("name")},
            "labels": [{"id": k, "label": names.get(k, k), "n": len(v2)}
                       for k, v2 in by.items()],
            "half_s": C.PETH_HALF_S, "bin_s": C.PETH_BIN_S,
            "cells": out}))

    @app.route("/api/cells/<gid>/bank", methods=["POST"])
    def api_cells_bank(gid):
        """One Cell entry per recording's sort: a row per cell (its first to
        its last spike), from the curation version picked. Banking again
        continues that entry."""
        body = request.get_json(force=True) or {}
        try:
            row, path, run, twin, art = resolve(gid)
            v = _pick_version(art, body.get("version"))
            pay = version_payload(art["id"], v)
            rows = pay.get("cells") or []
            if not rows:
                raise ValueError("v%d holds no cells." % v)
            events, names = [], {}
            for c in rows:
                if c.get("first_s") is None:
                    continue
                lid = "c%d" % int(c["id"])
                names[lid] = "Cell %d · CSC %d%s" % (
                    int(c["id"]), int(c["csc"]),
                    (" · " + c["layer_name"]) if c.get("layer_name") else "")
                events.append({"start": c["first_s"], "end": c["last_s"],
                               "label_id": lid, "label": names[lid],
                               "channel": int(c["csc"]),
                               "n_spikes": int(c["n"])})
            ent = entry_of(gid, run["path"])
            src = pay.get("source") or {}
            made = A.BANK.add({
                "id": ent["id"] if ent else None,
                "project": row.get("project"), "mouse": row.get("mouse"),
                "session": row.get("session"),
                "session_label": row.get("label"), "session_path": path,
                "gid": gid, "type": "cell", "type_name": "Cell",
                "label_names": names,
                "name": (str(body.get("name") or "").strip()
                         or "Cells · %s" % (row.get("label") or gid)),
                "note": ("%d curated cells of the Kilosort sort %s, from "
                         "curation v%d (%s). One row per cell, its first to "
                         "its last spike; the spikes stay in the sort "
                         "folder." % (len(events), run["name"], v,
                                      src.get("name")))
                        + ((" " + str(body.get("note")).strip())
                           if str(body.get("note") or "").strip() else ""),
                "events": events, "curated": True,
                "pipeline": PIPELINE,
                "added_by": (A.STORE.provenance() or {}).get("user"),
                "parameters": {"tool": "cells", "run": run["name"],
                               "run_dir": run["path"],
                               "twin": twin["name"] if twin else None,
                               "thresholds": {"Th_learned": 6,
                                              "Th_universal": 7}
                               if "tl6_tu7" in run["name"] else None,
                               "invert": False,
                               "curation": {"artifact_id": art["id"],
                                            "version": v,
                                            "source": src.get("kind"),
                                            "source_name": src.get("name")},
                               "polarity": pay.get("polarity")},
            })
        except A.eventbank.BankError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:                         # noqa: BLE001
            return A.fail("cells/bank", exc, 400, {"gid": gid})
        drop_scan()
        A.STORE.record_activity([{"action": "cells.bank", "detail": {
            "gid": gid, "id": made.get("id"), "cells": len(events),
            "version": v}}])
        A.mirror_bank_soon()
        return jsonify({"ok": True, "entry_id": made["id"],
                        "name": made.get("name"), "n": made.get("n"),
                        "new": not ent})
