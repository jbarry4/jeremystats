"""
figroutes.py -- the figure builder's routes (figkit + figures.py).

Kept out of app.py's thirty thousand lines because it is one feature with one
set of collaborators. `install(app, A)` is called once from app.py with app
itself as `A`, so the store, the session cache, the layer sheets and `fail`
are read off it when a request needs them rather than copied at import time.

    GET  /api/figkit/catalog              what can be drawn, units, profiles
    POST /api/figkit/frame                the page without its panels
    POST /api/figkit/tile                 one panel, alone, at its box
    POST /api/figkit/export               a new version: png + svg + pdf
    GET  /api/figures                     figures (?gid=, ?archived=1)
    POST /api/figures                     a new draft
    GET  /api/figures/<id>                one figure, every version
    POST /api/figures/<id>/draft          keep the draft
    POST /api/figures/<id>/archive        archive or bring back
    GET  /api/figures/<id>/v/<n>/file/<fmt>
"""
from __future__ import annotations

import base64
import os

from flask import Response, jsonify, request, send_file

from . import figkit
from . import figures as figuresmod
from . import layers as layersmod
from .figkit import render as figrender

FORMATS = ("png", "svg", "pdf")


class Ctx:
    """What an adapter may ask of the app while it draws."""

    def __init__(self, A, layout):
        self.A = A
        self.recording = dict((layout or {}).get("recording") or {})
        try:
            self.prov = A.STORE.provenance()
        except Exception:                                 # noqa: BLE001
            self.prov = {}

    def session(self, path, invert=True):
        sess, _err = self.A._session_for(path, bool(invert))
        return sess

    def anatomy(self, gid):
        """{channel number: region name} from the recording's layer sheet."""
        rec = self.A.LAYERS.get(gid)
        if not rec:
            return {}
        names = {r["id"]: r.get("name") or r["id"]
                 for r in layersmod.regions_for(rec)}
        out = {}
        for k, v in (rec.get("labels") or {}).items():
            if not v:
                continue
            try:
                out[int(k)] = names.get(v, v)
            except (TypeError, ValueError):
                continue
        return out


def install(app, A):
    figs = figuresmod.Figures(A.LOGS_DIR, A.STORE, A.outputs_dir())
    scratch = figuresmod.Figures(
        os.path.join(A.LOGS_DIR, ".cache", "figures_scratch"), None,
        os.path.join(A.outputs_dir(), A.SCRATCH_DIR))

    def book(body=None):
        """Harness pages save into the by-product lane, whose records are
        under the ignored cache and whose files are under Results/_scratch."""
        return scratch if A.lane_of(body) == A.SCRATCH_LANE else figs

    def err(exc):
        status = getattr(exc, "status", 400)
        return jsonify({"ok": False, "error": str(exc)}), status

    def body_layout():
        body = request.get_json(force=True, silent=True) or {}
        layout = body.get("layout") or {}
        if not isinstance(layout, dict):
            raise figkit.FigError("A figure layout is an object.")
        return body, layout

    @app.route("/api/figkit/catalog")
    def api_figkit_catalog():
        from . import analysis
        out = figkit.catalog()
        out["colormaps"] = [dict(c, swatch=analysis.colormap_swatch(c["id"],
                                                                    24))
                            for c in analysis.COLORMAPS]
        return jsonify(dict(out, ok=True))

    @app.route("/api/figkit/frame", methods=["POST"])
    def api_figkit_frame():
        try:
            body, layout = body_layout()
            got = figrender.render_frame(layout, Ctx(A, layout),
                                         dpi=int(body.get("dpi", 110)))
        except (figkit.FigError, ValueError) as exc:
            return err(exc)
        except Exception as exc:                          # noqa: BLE001
            return A.fail("figkit/frame", exc, 400)
        got["image"] = _uri(got["image"])
        return jsonify(dict(got, ok=True))

    @app.route("/api/figkit/tile", methods=["POST"])
    def api_figkit_tile():
        try:
            body, layout = body_layout()
            got = figrender.render_tile(layout, str(body.get("uid") or ""),
                                        Ctx(A, layout),
                                        dpi=int(body.get("dpi", 110)))
        except (figkit.FigError, ValueError) as exc:
            return err(exc)
        except Exception as exc:                          # noqa: BLE001
            return A.fail("figkit/tile", exc, 400)
        got["image"] = _uri(got["image"])
        return jsonify(dict(got, ok=True))

    @app.route("/api/figkit/export", methods=["POST"])
    def api_figkit_export():
        try:
            body, layout = body_layout()
            store = book(body)
            ctx = Ctx(A, layout)
            fid = body.get("figure_id") or layout.get("id")
            if fid:
                rec = store.get(fid)
            else:
                rec = store.create(layout, ctx.prov)
                fid = rec["id"]
            layout = dict(layout, id=fid, v=store.next_v(rec))
            blobs, P, problems = {}, None, []
            for fmt in [f for f in (body.get("formats") or FORMATS)
                        if f in FORMATS]:
                blob, probs, P = figrender.render_page(layout, ctx, fmt)
                blobs[fmt] = blob
                problems = probs
            if not blobs:
                raise figkit.FigError("Choose png, svg or pdf.")
            nums = figrender.numbers(layout, P)
            lin = figrender.lineage(layout, P, ctx)
            row = store.add_version(fid, layout, blobs, nums, lin, ctx.prov,
                                    note=body.get("note"),
                                    from_v=body.get("from_v"),
                                    source=body.get("source") or "builder")
        except (figkit.FigError, figuresmod.FigureError, ValueError) as exc:
            return err(exc)
        except Exception as exc:                          # noqa: BLE001
            return A.fail("figkit/export", exc, 400)

        run = None
        if store is figs:
            run = _record_run(A, store, fid, row, layout, problems)
        return jsonify({"ok": True, "figure": store.summary(store.get(fid)),
                        "version": _public(row), "problems": problems,
                        "run_id": (run or {}).get("id")})

    @app.route("/api/figures")
    def api_figures():
        store = book()
        return jsonify({"ok": True, "figures": store.list(
            gid=request.args.get("gid") or None,
            archived=bool(request.args.get("archived")))})

    @app.route("/api/figures", methods=["POST"])
    def api_figures_new():
        try:
            body, layout = body_layout()
            store = book(body)
            figrender.check_layout(layout)
            rec = store.create(layout, Ctx(A, layout).prov)
        except (figkit.FigError, figuresmod.FigureError) as exc:
            return err(exc)
        except Exception as exc:                          # noqa: BLE001
            return A.fail("figures/new", exc, 400)
        return jsonify({"ok": True, "figure": _full(store, rec)})

    @app.route("/api/figures/<fid>")
    def api_figure_get(fid):
        try:
            store = book()
            return jsonify({"ok": True, "figure": _full(store,
                                                        store.get(fid))})
        except figuresmod.FigureError as exc:
            return err(exc)

    @app.route("/api/figures/<fid>/draft", methods=["POST"])
    def api_figure_draft(fid):
        try:
            body, layout = body_layout()
            store = book(body)
            rec = store.save_draft(fid, layout)
        except (figkit.FigError, figuresmod.FigureError) as exc:
            return err(exc)
        except Exception as exc:                          # noqa: BLE001
            return A.fail("figures/draft", exc, 400)
        return jsonify({"ok": True, "figure": store.summary(rec)})

    @app.route("/api/figures/<fid>/archive", methods=["POST"])
    def api_figure_archive(fid):
        try:
            body = request.get_json(force=True, silent=True) or {}
            store = book(body)
            rec = store.archive(fid, body.get("on", True) is not False)
        except figuresmod.FigureError as exc:
            return err(exc)
        return jsonify({"ok": True, "figure": store.summary(rec)})

    @app.route("/api/figures/<fid>/v/<int:v>/file/<fmt>")
    def api_figure_file(fid, v, fmt):
        try:
            store = book()
            _rec, row = store.version(fid, v)
            rel = (row.get("files") or {}).get(fmt)
            if not rel:
                raise figuresmod.FigureError(
                    "Version %d has no %s." % (v, fmt.upper()), 404)
            full = store.full_path(rel)
            if not os.path.isfile(full):
                raise figuresmod.FigureError(
                    "The %s of version %d is not on this machine yet. A pull "
                    "brings it." % (fmt.upper(), v), 404)
        except figuresmod.FigureError as exc:
            return err(exc)
        from . import compose
        return send_file(full, mimetype=compose.MIME.get(fmt),
                         as_attachment=bool(request.args.get("download")),
                         download_name=os.path.basename(full))

    return figs


def _uri(png):
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _public(row):
    """A version row without its bulk -- the tree shows these."""
    return {k: row.get(k) for k in ("id", "v", "at", "by", "machine",
                                    "app_version", "commit", "digest",
                                    "files", "data", "note", "from_v",
                                    "source")}


def _full(store, rec):
    out = store.summary(rec)
    out["draft"] = rec.get("draft")
    out["versions"] = sorted(
        [dict(_public(v), layout=v.get("layout"), lineage=v.get("lineage"))
         for v in rec.get("versions") or []], key=lambda r: r.get("v") or 0)
    return out


def _record_run(A, store, fid, row, layout, problems):
    """A run record, so Results lists the files beside every other result
    and its Rebuild button knows which figure version they are."""
    rec = layout.get("recording") or {}
    outs = []
    for fmt in FORMATS:
        rel = (row.get("files") or {}).get(fmt)
        if rel:
            outs.append({"path": store.full_path(rel), "rel": rel,
                         "format": fmt})
    if not outs:
        return None
    try:
        run = A.STORE.record_run({
            "kind": "figure", "script": "Figure builder",
            "label": "%s v%d" % (layout.get("title") or "Figure", row["v"]),
            "status": "done", "format": outs[0]["format"],
            "parameters": {"figure_id": fid, "v": row["v"],
                           "profile": layout.get("profile"),
                           "width": layout.get("width"),
                           "panels": len(layout.get("panels") or [])},
            "panels": [{"tool": p.get("tool"), "plot": p.get("plot"),
                        "title": p.get("title")}
                       for p in layout.get("panels") or []],
            "recipe": {"schema": figuresmod.SCHEMA, "figure_id": fid,
                       "v": row["v"]},
            "session": {"gid": rec.get("gid"), "label": rec.get("label"),
                        "path": rec.get("path")},
            "output": outs[0], "outputs": outs,
            "problems": problems,
        })
        return run
    except Exception as exc:                              # noqa: BLE001
        A.STORE.record_error("figkit/run", "Could not record the run: %s"
                             % exc, None, {"figure": fid})
        return None
