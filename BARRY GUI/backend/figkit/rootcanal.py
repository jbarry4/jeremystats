"""
figkit/rootcanal.py -- Root Canal's pictures as figure panels.

Root Canal draws in the browser (the backend never draws, the rule dspca.py
keeps), and until now a Root Canal figure was those canvases pasted into a
PNG. Here the same answer is drawn by matplotlib, from the same numbers:

    a fit asked of the read on this machine -- app.py's own `_rootcanal_setup`
      and `rootcanal.fit`, the code Recompute runs, so the panel cannot
      disagree with the tool; or
    a saved version's numbers (an artifact), which open on any machine,
      when the panel names one (`params.artifact`).

A read that is on another machine and no saved version is a sentence, not a
guess (memory: Root Canal reads are machine-local).

One recording only: Root Canal's pooled view pools recordings and is not a
figure panel.

    plots   flat           the three flat views side by side
            amp_hw         amplitude against half-width
            amp_hf         amplitude against HF power
            hw_hf          half-width against HF power
            space          the three numbers z-scored, in 3D
"""
from __future__ import annotations

import numpy as np

from . import Adapter, FigError, register

AMP = {"quantity": "voltage", "unit": "µV", "words": "Amplitude"}
HW = {"quantity": "time", "unit": "ms", "words": "Half-width"}
HF = {"quantity": "power_db", "unit": "dB", "words": "HF power"}
DECL = {"amp_uV": AMP, "hw_ms": HW, "hf_db": HF}
PAIRS = {"amp_hw": ("amp_uV", "hw_ms"), "amp_hf": ("amp_uV", "hf_db"),
         "hw_hf": ("hw_ms", "hf_db")}

PLOTS = [
    {"id": "flat", "name": "The three flat views", "axes": {},
     "ytick_chars": 5, "stats": False},
    {"id": "amp_hw", "name": "Amplitude against half-width",
     "axes": {"x": AMP, "y": HW}, "ytick_chars": 4},
    {"id": "amp_hf", "name": "Amplitude against HF power",
     "axes": {"x": AMP, "y": HF}, "ytick_chars": 4},
    {"id": "hw_hf", "name": "Half-width against HF power",
     "axes": {"x": HW, "y": HF}, "ytick_chars": 4},
    {"id": "space", "name": "The three numbers, in 3D", "axes": {},
     "ytick_chars": 2},
    {"id": "pooled", "name": "Pooled recordings", "pooled": True, "axes": {}},
]

#: Colour-blind-safe and printable: dentate spikes in blue, IEDs in orange,
#: an event not measured on every axis hollow and grey.
COLOUR = {"ds": "#3B6FB6", "ied": "#E66101"}
UNMEASURED = "#8C8C8C"


class RootCanal(Adapter):
    tool = "rootcanal"
    name = "Root Canal"

    def plots(self):
        return PLOTS

    # ---------------------------------------------------------------
    def prepare(self, spec, ctx):
        A = getattr(ctx, "A", None)
        if A is None:
            raise FigError("Root Canal panels need the app to draw from.")
        q = dict(spec.get("params") or {})
        art = q.get("artifact") or {}
        res = None
        source = None
        if art.get("artifact_id"):
            payload = A.ARTIFACTS.payload(art["artifact_id"], art.get("v"))
            if payload is None:
                raise FigError(
                    "That saved version of Root Canal was made on another "
                    "machine and its numbers have not reached this one yet.")
            from .. import rootcanal as rc
            res = rc.single_fit_view(payload)
            source = (("from saved version v%s" % art["v"]) if art.get("v")
                      else "from its latest saved version")
        else:
            try:
                rec, p, got, _rh, _stamps = A._rootcanal_setup(q)
                margin, _used = A._rootcanal_margin_for(p)
                from .. import rootcanal as rc
                res = rc.fit(got, p, margin=margin)
                source = "fitted from the read on this machine"
            except Exception as exc:                      # noqa: BLE001
                raise FigError(str(exc))
        events = res.get("events") or []
        if not events:
            raise FigError("This Root Canal answer has no events in it.")
        cols = {k: np.array([np.nan if e.get(k) is None else float(e[k])
                             for e in events]) for k in DECL}
        cls = [e.get("cls") for e in events]
        out = {"res": res, "cols": cols, "cls": cls, "source": source,
               "z": [e.get("z") for e in events],
               "centres": res.get("centres") or []}
        if spec.get("plot") in PAIRS:
            xa, ya = PAIRS[spec["plot"]]
            out["lim"] = {"x": _span(cols[xa]), "y": _span(cols[ya])}
        return out

    # ---------------------------------------------------------------
    def draw(self, fig, rect, spec, prep, ctx, st):
        plot = spec.get("plot")
        if plot in PAIRS:
            ax = fig.add_axes(rect)
            xa, ya = PAIRS[plot]
            self._scatter(ax, prep, xa, ya, st)
            self._legend(ax, prep, st)
            return {"main": ax, "axes": [ax]}
        if plot == "flat":
            fw, fh = fig.get_size_inches()
            gap = 0.42 / fw
            w = (rect[2] - 2 * gap) / 3.0
            axes = []
            for i, (xa, ya) in enumerate(PAIRS.values()):
                ax = fig.add_axes([rect[0] + i * (w + gap), rect[1], w,
                                   rect[3]])
                self._scatter(ax, prep, xa, ya, st)
                ax.set_xlabel(_words(xa), fontsize=st.sizes["label"],
                              color=st.ink, family=st.font)
                ax.set_ylabel(_words(ya), fontsize=st.sizes["label"],
                              color=st.ink, family=st.font)
                axes.append(ax)
            self._legend(axes[-1], prep, st)
            return {"main": axes[0], "axes": axes}
        if plot == "space":
            from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
            ax = fig.add_axes(rect, projection="3d")
            view = (spec.get("params") or {}).get("view") or {}
            ax.view_init(elev=float(view.get("elev", 22)),
                         azim=float(view.get("azim", -58)))
            z = prep["z"]
            for kind in ("ds", "ied"):
                pts = np.array([zz for zz, c in zip(z, prep["cls"])
                                if c == kind and zz and None not in zz],
                               dtype=float)
                if pts.size:
                    ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], s=6,
                               color=COLOUR[kind], depthshade=False,
                               linewidths=0)
            for c in prep["centres"]:
                cz = c.get("z") or []
                if len(cz) == 3:
                    ax.scatter([cz[0]], [cz[1]], [cz[2]], s=40, marker="+",
                               color=st.ink, linewidths=st.line * 1.6)
            for setter, name in ((ax.set_xlabel, "amp_uV"),
                                 (ax.set_ylabel, "hw_ms"),
                                 (ax.set_zlabel, "hf_db")):
                setter(DECL[name]["words"] + " (z)",
                       fontsize=st.sizes["small"], family=st.font)
            ax.tick_params(labelsize=st.sizes["small"] * 0.9)
            from matplotlib.ticker import MaxNLocator
            for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
                axis.set_major_locator(MaxNLocator(4))
            self._legend(ax, prep, st)
            return {"main": ax, "axes": []}
        raise FigError("Root Canal has no plot called %s." % plot)

    def _scatter(self, ax, prep, xa, ya, st):
        x, y = prep["cols"][xa], prep["cols"][ya]
        both = np.isfinite(x) & np.isfinite(y)
        cls = np.array([c or "" for c in prep["cls"]])
        for kind in ("ds", "ied"):
            m = both & (cls == kind)
            if m.any():
                ax.scatter(x[m], y[m], s=7, color=COLOUR[kind], linewidths=0,
                           zorder=3, label=None)
        m = both & ~np.isin(cls, ["ds", "ied"])
        if m.any():
            ax.scatter(x[m], y[m], s=7, facecolors="none",
                       edgecolors=UNMEASURED, linewidths=st.line, zorder=2)
        for c in prep["centres"]:
            raw = c.get("raw") or []
            ix, iy = ["amp_uV", "hw_ms", "hf_db"].index(xa), \
                ["amp_uV", "hw_ms", "hf_db"].index(ya)
            if len(raw) == 3 and raw[ix] is not None and raw[iy] is not None:
                ax.plot([raw[ix]], [raw[iy]], marker="+", markersize=7,
                        color=st.ink, markeredgewidth=st.line * 1.8, zorder=5)
        if ya == "hf_db":
            lo, hi = _span(y)
            if lo < 0 < hi:
                ax.axhline(0, color=st.muted, linewidth=st.line * 0.7,
                           linestyle=(0, (2, 2)), zorder=1)

    def _legend(self, ax, prep, st):
        counts = (prep["res"].get("counts") or {})
        bits = []
        for kind, word in (("ds", "DS"), ("ied", "IED")):
            n = counts.get(kind)
            if n is None:
                n = sum(1 for c in prep["cls"] if c == kind)
            bits.append((COLOUR[kind], "%s  %d" % (word, n)))
        y = 0.98
        for colour, text in bits:
            put = getattr(ax, "text2D", None) or ax.text   # a 3D axes
            put(0.98, y, text, transform=ax.transAxes, ha="right",
                va="top", fontsize=st.sizes["small"], color=colour,
                family=st.font, weight="bold")
            y -= st.sizes["small"] * 1.5 / 72.0 / max(
                0.3, ax.get_position().height * ax.figure.get_size_inches()[1])

    # ---------------------------------------------------------------
    def lineage(self, spec, prep, ctx):
        q = spec.get("params") or {}
        res = (prep or {}).get("res") or {}
        counts = res.get("counts") or {}
        bits = ["set %s" % q.get("entry_id")]
        if q.get("from_version"):
            bits.append("version %s" % q["from_version"])
        filt = q.get("filt")
        if q.get("lo_hz") is not None and q.get("hi_hz") is not None:
            bits.append("%s filter %g-%g Hz%s" % (
                (filt or "custom").upper() if filt in ("ds", "lfp") else
                (filt or "custom"), float(q["lo_hz"] or 0),
                float(q["hi_hz"] or 0),
                ", mains out" if q.get("mains_out") else ""))
        if q.get("win_ms") is not None:
            bits.append("±%g ms" % float(q["win_ms"]))
        if q.get("band_lo") is not None:
            bits.append("HF %g-%g Hz" % (float(q["band_lo"]),
                                         float(q["band_hi"])))
        if q.get("k"):
            bits.append("k = %s" % q["k"])
        if counts:
            bits.append("%s DS, %s IED%s" % (
                counts.get("ds", 0), counts.get("ied", 0),
                (", %s not measured" % counts["unmeasured"])
                if counts.get("unmeasured") else ""))
        if q.get("flips"):
            bits.append("%d flipped by hand" % len(q["flips"]))
        if (prep or {}).get("source"):
            bits.append(prep["source"])
        return {"phrases": bits, "fields": {
            "tool": "rootcanal", "plot": spec.get("plot"),
            "entry_id": q.get("entry_id"),
            "from_version": q.get("from_version"),
            "artifact": q.get("artifact"), "counts": counts,
            "rule": res.get("rule"), "params": q}}

    def numbers(self, spec, prep):
        prep = prep or {}
        cols = prep.get("cols") or {}
        out = {k: v for k, v in cols.items()}
        out["is_ied"] = np.array([1 if c == "ied" else (0 if c == "ds" else -1)
                                  for c in prep.get("cls") or []], dtype=np.int8)
        ev = (prep.get("res") or {}).get("events") or []
        out["t"] = np.array([float(e.get("t") or 0) for e in ev])
        return out


def _span(v):
    v = np.asarray(v, dtype=float)
    v = v[np.isfinite(v)]
    if not v.size:
        return [0.0, 1.0]
    lo, hi = float(v.min()), float(v.max())
    pad = (hi - lo) * 0.06 or 1.0
    return [lo - pad, hi + pad]


def _words(axis):
    d = DECL[axis]
    return "%s (%s)" % (d["words"], d["unit"])


register(RootCanal())
