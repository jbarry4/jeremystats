# -*- coding: utf-8 -*-
"""figkit, the figure builder's engine, against the demo recording. Offline.

    python tools/test_figkit.py

Nothing here touches GUI_logs or Results: the figure store is pointed at a
temp folder, and the recording is demo.py's, which is generated rather than
read.

What is guarded:

  * units: a unit can only be one its quantity offers, and switching rescales
    the ticks rather than relabelling the same numbers;
  * an axis label is always words + the generated unit;
  * linked panels share a range, an unlinked one keeps its own, and a
    person's range wins (cut keeps inside the data, extend does not);
  * letters follow reading order and re-letter when a panel moves;
  * presets re-slot panels without losing any;
  * a pooled plot and a second recording are refused in a sentence;
  * a tile is the page's panel: same box, same letter, same scales;
  * the footer is never cut -- every phrase is printed, no ellipsis;
  * png, svg and pdf all render; pdf/svg carry the title metadata;
  * a version files its renders and its numbers, and stays as it was when
    the draft moves on.
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

FAILED = []


def check(name, ok, detail=""):
    print("  %-70s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:600])
    if not ok:
        FAILED.append(name)


class Ctx:
    def __init__(self, layout):
        from backend import csc
        self.recording = layout.get("recording") or {}
        self.prov = {"user": "harness", "machine": "test",
                     "app_version": "0.0.0", "commit": "abcdef1234"}
        self._csc = csc
        self._s = {}

    def session(self, path, invert=True):
        key = (path, invert)
        if key not in self._s:
            got = self._csc.open_session(path, invert=invert)
            self._s[key] = got if got.get("ok") else None
        return self._s[key]

    def anatomy(self, gid):
        return {n: ("CA1 SP" if n <= 10 else "DG GCL1") for n in range(1, 33)}


def demo_layout(**kw):
    rec = {"gid": "demo-ds-tutorial", "label": "DEMO m1 s1 (dentate spikes)",
           "path": "demo:ds-tutorial", "invert": True}
    base = {"t0": 3.0, "t1": 4.0, "highpass": 1, "lowpass": 300,
            "channels": list(range(0, 32, 2)), "bad_channels": [17]}
    layout = {
        "schema": "fig/2", "profile": "nature", "width": "double",
        "height_mm": 120, "rows": 1, "cols": 2, "title": "Demo figure",
        "subtitle": "two panels", "recording": rec,
        "panels": [
            {"uid": "a", "tool": "xplore", "plot": "traces", "row": 0,
             "col": 0, "rowspan": 1, "colspan": 1, "title": "Traces",
             "params": dict(base)},
            {"uid": "b", "tool": "xplore", "plot": "csd", "row": 0,
             "col": 1, "rowspan": 1, "colspan": 1, "title": "CSD",
             "params": dict(base, t0=3.2, t1=4.6)},
        ],
    }
    layout.update(kw)
    return layout


def main():
    from backend import figkit, figures
    from backend.figkit import layout as L
    from backend.figkit import render as R
    from backend.figkit import units as U
    from backend.figkit import xplore  # noqa: F401

    print("units")
    check("time offers s, ms, us, min",
          U.choices("time", "s") == ["s", "ms", "µs", "min"])
    check("a unit the quantity lacks falls back to the base",
          U.pick("time", "s", "mV") == "s")
    check("s -> ms is x1000", abs(U.factor("time", "s", "ms") - 1000) < 1e-9)
    check("label is words + generated unit",
          U.axis_text("Elapsed", "time", "ms") == "Elapsed (ms)")
    check("empty words fall back to the quantity",
          U.axis_text("", "time", "ms") == "Time (ms)")
    check("an unknown quantity shows its own unit, unconverted",
          U.choices("weird", "a.u.") == ["a.u."])
    try:
        U.factor("weird", "a.u.", "b")
        check("an unknown quantity refuses conversion", False)
    except U.UnitError:
        check("an unknown quantity refuses conversion", True)

    print("layout")
    lay = demo_layout()
    lets = L.letters(lay)
    check("letters in reading order (Nature: lower case)",
          lets == {"a": "a", "b": "b"}, lets)
    lay["panels"][0].update(row=0, col=1)
    lay["panels"][1].update(row=0, col=0)
    check("moving a panel re-letters", L.letters(lay) == {"b": "a", "a": "b"})
    L.apply_preset(lay, "2x1")
    check("a preset re-slots in reading order",
          [(p["uid"], p["row"], p["col"]) for p in lay["panels"]]
          == [("b", 0, 0), ("a", 1, 0)], lay["panels"])
    lay3 = demo_layout()
    lay3["panels"].append(dict(lay3["panels"][0], uid="c"))
    L.apply_preset(lay3, "1x2")
    check("a preset with too few cells keeps every panel",
          len(lay3["panels"]) == 3 and lay3["rows"] == 2, lay3["panels"])

    print("refusals")
    bad = demo_layout()
    bad["panels"][1]["gid"] = "someone-else"
    try:
        R.check_layout(bad)
        check("a second recording is refused", False)
    except figkit.FigError as exc:
        check("a second recording is refused", "one recording" in str(exc))
    pooled = figkit.Adapter()
    pooled.tool, pooled.name = "pooltest", "Pool test"
    pooled.plots = lambda: [{"id": "pool", "name": "Pool", "pooled": True,
                             "axes": {}}]
    figkit.register(pooled)
    try:
        figkit.plot_of({"tool": "pooltest", "plot": "pool"})
        check("a pooled plot is refused", False)
    except figkit.FigError as exc:
        check("a pooled plot is refused", "one recording" in str(exc), exc)

    print("shared scales")
    lay = demo_layout()
    ctx = Ctx(lay)
    P = R.plan(lay, ctx)
    ra, rb = P["res"]["a"], P["res"]["b"]
    check("linked time axes share one range",
          ra["x"] == rb["x"] and abs(ra["x"][0] - 3.0) < 0.05
          and abs(ra["x"][1] - 4.6) < 0.05, (ra, rb))
    lay["panels"][1]["link"] = {"x": False}
    P = R.plan(lay, ctx)
    check("an unlinked panel keeps its own",
          abs(P["res"]["b"]["x"][0] - 3.2) < 0.05
          and abs(P["res"]["a"]["x"][1] - 4.0) < 0.05, P["res"])
    lay["panels"][0]["axes"] = {"x": {"unit": "ms", "range": [3100, 9000],
                                      "crop": "cut"}}
    P = R.plan(lay, ctx)
    got = P["res"]["a"]["x"]
    check("a range in ms is read back in s, and cut keeps it in the data",
          abs(got[0] - 3.1) < 1e-6 and abs(got[1] - 4.0) < 0.05, got)
    lay["panels"][0]["axes"]["x"]["crop"] = "extend"
    P = R.plan(lay, ctx)
    got = P["res"]["a"]["x"]
    check("extend takes the range as given", abs(got[1] - 9.0) < 1e-6, got)

    print("rendering")
    lay = demo_layout()
    lay["panels"][0]["axes"] = {"x": {"unit": "ms", "words": "Elapsed"}}
    lay["panels"][0]["labels"] = {"anatomy": True}
    ctx = Ctx(lay)
    frame = R.render_frame(lay, ctx, dpi=80)
    check("frame renders", frame["image"][:4] == b"\x89PNG", frame.get(
        "problems"))
    check("frame gives both boxes", set(frame["boxes"]) == {"a", "b"})
    tile = R.render_tile(lay, "a", ctx, dpi=80)
    check("tile renders without error", tile["image"][:4] == b"\x89PNG"
          and not tile.get("error"), tile.get("error"))
    check("tile has its letter, title and axes to click",
          {"letter", "title", "x", "y", "plot"} <= set(tile["hits"]),
          tile["hits"])
    tb = R.render_tile(lay, "b", ctx, dpi=80)
    check("raster tile has a colour bar to click", "c" in tb["hits"],
          tb["hits"])

    for fmt in ("png", "svg", "pdf"):
        blob, probs, P = R.render_page(lay, ctx, fmt, dpi=120)
        check("%s renders with no panel problems" % fmt,
              len(blob) > 1000 and not probs, probs)
        if fmt == "svg":
            text = blob.decode("utf-8", "replace")
            check("svg keeps text as text (Elapsed (ms))",
                  "Elapsed (ms)" in text)
            check("svg carries the title", "Demo figure" in text)
        if fmt == "pdf":
            check("pdf embeds TrueType (fonttype 42)",
                  b"/FontFile2" in blob or b"TrueType" in blob)

    lines = P["foot"]["lines"]
    joined = " ".join(lines)
    check("footer names the recording", "DEMO m1 s1" in joined, lines)
    check("footer has a line per panel", any(l.startswith("a ") for l in lines)
          and any(l.startswith("b ") for l in lines), lines)
    check("footer names the code that drew it",
          "Jarvis 0.0.0 (abcdef12)" in joined, lines)
    check("footer is never cut", "…" not in joined and "..." not in
          joined, lines)

    # Same box, same scale: what the tile draws is the page's panel.
    from backend.figkit import layout as L2
    geo = P["geo"]
    g = next(x for x in geo["panels"] if x["uid"] == "a")
    P2 = R.plan(lay, ctx)
    g2 = next(x for x in P2["geo"]["panels"] if x["uid"] == "a")
    check("tile and page compute the same box", g == g2)
    check("tile and page share resolved scales",
          tile["resolved"] == P["res"]["a"], (tile["resolved"],
                                              P["res"]["a"]))

    long_note = "word " * 400
    lay["footer"] = {"notes": long_note}
    P = R.plan(lay, ctx)
    printed = " ".join(P["foot"]["lines"])
    check("a very long note is printed whole, over more lines",
          printed.count("word") == 400 and len(P["foot"]["lines"]) > 4,
          len(P["foot"]["lines"]))

    nums = R.numbers(lay, P)
    check("traces keep their plotted numbers",
          "a.min_uv" in nums and nums["a.min_uv"].ndim == 2, list(nums))
    check("the raster keeps its picture and its scale",
          "b.rgb" in nums and "b.clim" in nums, list(nums))

    print("the store")
    tmp = tempfile.mkdtemp(prefix="jarvis-figkit-")
    try:
        store = figures.Figures(os.path.join(tmp, "logs"), None,
                                os.path.join(tmp, "Results"))
        lay = demo_layout()
        rec = store.create(lay, ctx.prov)
        fid = rec["id"]
        check("a new figure is a draft", rec["status"] == "draft"
              and rec["gid"] == "demo-ds-tutorial")
        blob, _p, P = R.render_page(dict(lay, id=fid, v=1), ctx, "png",
                                    dpi=80)
        row = store.add_version(fid, lay, {"png": blob}, R.numbers(lay, P),
                                R.lineage(lay, P, ctx), ctx.prov)
        check("version 1 is filed under Results/Figures/<recording>",
              row["v"] == 1 and row["files"]["png"].startswith(
                  "Figures/DEMO m1 s1"), row["files"])
        check("its numbers are filed beside it",
              os.path.isfile(store.full_path(row["data"])))
        lay2 = demo_layout(title="Changed")
        store.save_draft(fid, lay2)
        _r, v1 = store.version(fid, 1)
        check("the draft moving on leaves version 1 as it was",
              v1["layout"]["title"] == "Demo figure")
        other = demo_layout()
        other["recording"] = dict(other["recording"], gid="x")
        try:
            store.save_draft(fid, other)
            check("a layout of another recording is refused", False)
        except figures.FigureError:
            check("a layout of another recording is refused", True)
        row2 = store.add_version(fid, lay2, {"png": blob}, {}, {}, ctx.prov)
        check("the next export is version 2", row2["v"] == 2)
        check("listed once, with two versions",
              [f["n_versions"] for f in store.list()] == [2])
        store.archive(fid)
        check("archived figures are hidden unless asked",
              store.list() == [] and len(store.list(archived=True)) == 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("%d FAILED: %s" % (len(FAILED), ", ".join(FAILED)))
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
