"""
figkit/xplore.py -- Xplorefinder's seven panels, as figkit panels.

The drawing is compose.py's, unchanged: traces, the rasters, the
time-frequency maps and the whole-probe panel are the same functions the
builder has always printed with. What is new is the half around them -- the
numbers read once in `prepare` so panels can agree on a scale before any is
drawn, the axes declared with their quantities so units can be switched
without being typed, and a lineage that says exactly which seconds, channels
and filters a panel is of.

A panel's `params` are what the pane on screen was asking the server for:
t0, t1, highpass, lowpass, notch, channels (indices), bad_channels (CSC
numbers), spacing_um, gain, cmap, clim, ylim, events, and for the
time-frequency panels tf_channels, tf_mode, fmin, fmax, fview_min,
fview_max, stft_mode; for the probe panel probe, probe_view, probe_columns.
"""
from __future__ import annotations

import numpy as np

from . import Adapter, FigError, register

TIME = {"quantity": "time", "unit": "s", "words": "Time"}
CHAN = {"quantity": "channel", "unit": "", "words": "Channel",
        "own_ticks": True, "own_limits": True}
FREQ = {"quantity": "frequency", "unit": "Hz", "words": "Frequency"}

PLOTS = [
    {"id": "traces", "name": "Voltage traces", "scalebar": True,
     "anatomy": True, "ytick_chars": 9,
     "axes": {"x": TIME, "y": CHAN}},
    {"id": "voltage", "name": "Voltage raster", "anatomy": True,
     "ytick_chars": 9,
     "axes": {"x": TIME, "y": CHAN,
              "c": {"quantity": "voltage", "unit": "µV",
                    "words": "Voltage"}}},
    {"id": "csd", "name": "CSD raster", "anatomy": True, "ytick_chars": 9,
     "axes": {"x": TIME, "y": CHAN,
              "c": {"quantity": "csd", "unit": "µA/mm³",
                    "words": "CSD"}}},
    {"id": "theta", "name": "Theta CSD", "anatomy": True, "ytick_chars": 9,
     "axes": {"x": TIME, "y": CHAN,
              "c": {"quantity": "csd", "unit": "µA/mm³",
                    "words": "Theta CSD"}}},
    {"id": "bandpower", "name": "Theta power, band by band",
     "ytick_chars": 5,
     "axes": {"x": TIME, "y": FREQ,
              "c": {"quantity": "power_db", "unit": "dB", "words": "Power"}}},
    {"id": "spectrogram", "name": "Spectrogram", "ytick_chars": 6,
     "axes": {"x": TIME, "y": FREQ,
              "c": {"quantity": "power_db", "unit": "dB", "words": "Power"}}},
    {"id": "scalogram", "name": "Scalogram", "ytick_chars": 6,
     "axes": {"x": TIME, "y": FREQ,
              "c": {"quantity": "power_db", "unit": "dB", "words": "Power"}}},
]

#: The params that change what is drawn, and so belong on the record. The
#: rest of what a pane carries (its colour chip, its scroll) does not.
PARAMS = ("t0", "t1", "highpass", "lowpass", "notch", "channels",
          "bad_channels", "spacing_um", "gain", "cmap", "clim", "ylim",
          "normalize", "tf_channels", "tf_mode", "fmin", "fmax", "fview_min",
          "fview_max", "stft_mode", "probe", "probe_view", "probe_columns",
          "channel", "smooth", "band_scale", "dyn_range_db", "clim_pct",
          "events")

MAX_EVENTS = 4000


def clean_params(params):
    out = {k: params[k] for k in PARAMS if k in (params or {})
           and params[k] is not None}
    ev = out.get("events")
    if isinstance(ev, list) and len(ev) > MAX_EVENTS:
        out["events"] = ev[:MAX_EVENTS]
        out["events_dropped"] = len(ev) - MAX_EVENTS
    return out


class Xplore(Adapter):
    tool = "xplore"
    name = "Xplorefinder"
    #: Colour is a re-render for these panels (the raster is a picture the
    #: analysis encodes), so a shared scale asks for the panel again.
    recolour = True

    def plots(self):
        return PLOTS

    # ---------------------------------------------------------------
    def _session(self, ctx):
        rec = getattr(ctx, "recording", None) or {}
        path = rec.get("path")
        if not path:
            raise FigError("This figure does not say which recording it is "
                           "of, so there is nothing to read.")
        sess = ctx.session(path, rec.get("invert", True))
        if not sess:
            raise FigError("The recording at %s could not be opened here."
                           % path)
        return sess

    def _spec(self, spec):
        """The request compose.py and analysis.py take: the params, plus
        which panel."""
        p = dict(spec.get("params") or {})
        p["panel"] = spec.get("plot")
        p.setdefault("t0", 0.0)
        p.setdefault("t1", float(p["t0"]) + 2.0)
        res = spec.get("_resolved") or {}
        if res.get("c") and spec.get("plot") != "traces":
            p["clim"] = list(res["c"])
        if spec.get("plot") in ("spectrogram", "scalogram"):
            if p.get("tf_channels") and len(p["tf_channels"]) == 1:
                p["channel"] = p["tf_channels"][0]
        return p

    def prepare(self, spec, ctx):
        from .. import analysis, compose, csc
        sess = self._session(ctx)
        p = self._spec(spec)
        kind = spec.get("plot")
        t0, t1 = float(p["t0"]), float(p["t1"])
        out = {"kind": kind, "t0": t0, "t1": t1,
               "n_channels": len(sess.get("channels") or []),
               "fs": sess.get("fs"), "name": sess.get("name")}

        if p.get("probe_view") and p.get("probe"):
            cols = compose._probe_columns(sess, p)
            if not cols:
                raise FigError("None of this probe's channels are in that "
                               "recording, so there are no columns to draw.")
            shared = compose._shared_scale(sess, p, cols, kind)
            out.update(probe=True, columns=cols, shared=shared)
            out["lim"] = {"x": [t0, t1]}
            if kind != "traces" and shared.get("clim"):
                out["clim_used"] = list(shared["clim"])
                out["lim"]["c"] = list(shared["clim"])
                out["cmap"] = p.get("cmap") or "jet"
            return out

        if kind == "traces":
            win = csc.get_window(
                sess, t0, t1, channels=p.get("channels"),
                px=int(p.get("px", 2200)),
                highpass=float(p.get("highpass", 0) or 0),
                lowpass=float(p.get("lowpass", 0) or 0),
                notch=float(p.get("notch", 0) or 0), mode="voltage",
                spacing_um=float(p.get("spacing_um", 50) or 50),
                ylim=p.get("ylim"))
            if not win.get("ok"):
                raise FigError(win.get("error") or "Could not read that "
                               "window.")
            out["win"] = win
            out["lim"] = {"x": [float(win["t0"]), float(win["t1"])]}
            return out

        panel = analysis.render_panel(sess, p)
        if not panel.get("ok", True):
            raise FigError(panel.get("error") or "That panel would not draw.")
        ext = panel["extent"]
        out["panel"] = panel
        out["clim_used"] = list(panel["clim"])
        out["cmap"] = panel.get("cmap") or p.get("cmap") or "jet"
        out["lim"] = {"x": [float(ext[0]), float(ext[1])],
                      "c": list(panel.get("clim_auto") or panel["clim"])}
        if panel.get("clim_manual"):
            out["lim"]["c"] = list(panel["clim"])
        stacked = panel.get("stacked") or (
            kind in ("spectrogram", "scalogram")
            and not panel.get("channel") and panel.get("channels_used")
            and len(panel["channels_used"]) > 1
            and panel.get("tf_mode") == "stack")
        if kind in ("bandpower", "spectrogram", "scalogram") and not stacked:
            out["lim"]["y"] = [float(ext[2]), float(ext[3])]
        axes = {}
        if stacked:
            axes["y"] = dict(CHAN)
        units = str(panel.get("units") or "")
        if kind == "bandpower" and "dB" not in units:
            axes["c"] = {"quantity": "psd", "unit": "µV²"}
        if axes:
            out["axes"] = axes
        return out

    # ---------------------------------------------------------------
    def draw(self, fig, rect, spec, prep, ctx, st):
        from .. import compose
        sess = self._session(ctx)
        p = self._spec(spec)
        p["colorbar"] = False

        if prep.get("probe"):
            from matplotlib.gridspec import GridSpec
            gs = GridSpec(1, 1, figure=fig, left=rect[0], bottom=rect[1],
                          right=rect[0] + rect[2], top=rect[1] + rect[3])
            q = dict(p, row=0, col=0, rowspan=1, colspan=1, title="")
            for k, v in (prep.get("shared") or {}).items():
                q[k] = v
            if prep.get("clim_used"):
                q["clim"] = prep["clim_used"]
            before = list(fig.axes)
            compose._draw_probe_panel(fig, gs, q, sess, q, 1, 1,
                                      {"gain": p.get("gain")}, st)
            drawn = [a for a in fig.axes if a not in before]
            if not drawn:
                raise FigError("The probe panel drew nothing.")
            main = drawn[len(drawn) // 2]
            cax = None
            if spec.get("plot") != "traces" and prep.get("clim_used"):
                cax = _colorbar(fig, drawn[-1], prep["clim_used"],
                                prep.get("cmap") or "jet", st)
            return {"main": main, "axes": drawn, "cbar": cax}

        ax = fig.add_axes(rect)
        # compose's lane note says "uV" in a ten-digit float; the figure
        # says it in µV or mV, rounded, or leaves it to the scale bars.
        p["show_scale"] = False
        if spec.get("plot") == "traces":
            compose._draw_traces(ax, sess, p, {"gain": p.get("gain")}, st,
                                 win=prep.get("win"))
            ax.grid(False)
            if not (spec.get("labels") or {}).get("scalebar"):
                win = prep.get("win") or {}
                gain = float(p.get("gain", 1.0) or 1.0)
                lane = float(win.get("robust_max") or 1.0) * 2.0 / (gain or 1)
                ax.text(1.0, 1.0, "one lane = %s" % _say_volt(_round3(lane)),
                        transform=ax.transAxes, ha="right", va="bottom",
                        fontsize=st.sizes["small"], color=st.muted,
                        family=st.font)
            return {"main": ax, "axes": [ax]}
        compose._draw_image_panel(ax, sess, p, st, panel=prep.get("panel"))
        # compose titles a one-channel map with its channel when the panel
        # has no title of its own. A figkit panel's title is drawn beside its
        # letter instead, and the channel is in the footer.
        ax.set_title("")
        cax = _colorbar(fig, ax, prep["clim_used"], prep.get("cmap") or "jet",
                        st)
        return {"main": ax, "axes": [ax], "cbar": cax}

    # ---------------------------------------------------------------
    def scalebar(self, ax, spec, prep, st):
        """A time bar and an amplitude bar where the axes were."""
        win = (prep or {}).get("win")
        if not win:
            return False
        p = spec.get("params") or {}
        gain = float(p.get("gain", 1.0) or 1.0)
        scale = float(win.get("robust_max") or 1.0)
        # One lane is 2.0 data units tall and holds scale/gain microvolts.
        uv_per_unit = scale / (gain or 1.0)
        t0, t1 = ax.get_xlim()
        tbar = _nice((t1 - t0) * 0.2)
        vbar = _nice(uv_per_unit * 1.6)
        y0 = ax.get_ylim()[0]
        x0 = t1 - tbar
        h = vbar / uv_per_unit
        kw = dict(color=st.ink, linewidth=st.line * 2.0, solid_capstyle="butt",
                  clip_on=False, zorder=9)
        ax.plot([x0, t1], [y0, y0], **kw)
        ax.plot([t1, t1], [y0, y0 + h], **kw)
        ax.text((x0 + t1) / 2.0, y0, _say_time(tbar), ha="center", va="top",
                fontsize=st.sizes["small"], color=st.ink, family=st.font)
        ax.text(t1, y0 + h / 2.0, " " + _say_volt(vbar), ha="left",
                va="center", fontsize=st.sizes["small"], color=st.ink,
                family=st.font, clip_on=False)
        ax.set_xticks([])
        ax.set_xlabel("")
        for s in ("bottom",):
            ax.spines[s].set_visible(False)
        return True

    def anatomy(self, spec, prep, ctx):
        """Region names, when the recording's layers have been labelled.

        Asked of `ctx.anatomy(gid)` -- the layer sheets (layers.py) live in
        app.py's world -- as {channel number: region name}, and grouped here
        into runs of neighbouring rows, in this panel's row coordinates.
        """
        look = getattr(ctx, "anatomy", None)
        rec = getattr(ctx, "recording", None) or {}
        if not look or not rec.get("gid"):
            return []
        try:
            names = look(rec["gid"]) or {}
        except Exception:                                 # noqa: BLE001
            return []
        rows = _row_numbers(prep)
        if not rows or not names:
            return []
        n = len(rows)
        runs = []
        for i, num in enumerate(rows):
            name = names.get(int(num))
            if runs and runs[-1][2] == name and runs[-1][1] == i - 1:
                runs[-1][1] = i
            else:
                runs.append([i, i, name])
        out = []
        for a, b, name in runs:
            if not name:
                continue
            # Traces stack top-down at 2.0 a lane; rasters at 1.0 a row
            # from the top of the extent.
            if prep.get("win"):
                ys = [(n - 1 - a) * 2.0, (n - 1 - b) * 2.0]
                out.append((min(ys) - 1.0, max(ys) + 1.0, name))
            else:
                ys = [n - a, n - b]
                out.append((min(ys) - 0.5, max(ys) + 0.5, name))
        out.sort()
        return out

    # ---------------------------------------------------------------
    def lineage(self, spec, prep, ctx):
        from .. import compose
        p = spec.get("params") or {}
        prep = prep or {}
        bits = []
        t0, t1 = float(p.get("t0", 0) or 0), float(p.get("t1", 0) or 0)
        bits.append("%.3f-%.3f s" % (t0, t1))
        filt = []
        for key, tag in (("highpass", "HP"), ("lowpass", "LP"),
                         ("notch", "notch")):
            if p.get(key):
                filt.append("%s %g" % (tag, float(p[key])))
        bits.append(" / ".join(filt) + " Hz" if filt else "unfiltered")
        chans = None
        if spec.get("plot") in ("spectrogram", "scalogram", "bandpower"):
            chans = p.get("tf_channels") or ([p["channel"]]
                                            if p.get("channel") is not None
                                            else None)
        chans = chans if chans is not None else p.get("channels")
        sess = None
        try:
            sess = self._session(ctx)
        except FigError:
            sess = None
        total = len((sess or {}).get("channels") or []) or prep.get(
            "n_channels") or 0
        nums = compose._numbers_for(sess, chans) if sess and chans else []
        if nums and total and len(nums) == total:
            bits.append("all %d channels" % total)
        elif nums:
            bits.append("CSC %s" % compose._ranges(nums))
        if spec.get("plot") in ("spectrogram", "scalogram") and nums \
                and len(nums) > 1:
            bits.append({"mean": "averaged", "stack": "stacked"}.get(
                p.get("tf_mode") or "stack", str(p.get("tf_mode"))))
        if p.get("probe_view"):
            cols = p.get("probe_columns")
            bits.append("probe columns %s" % ", ".join(cols) if cols
                        else "every probe column")
        bad = [int(b) for b in (p.get("bad_channels") or [])]
        if bad:
            bits.append("bad CSC " + compose._ranges(bad))
        if p.get("gain") and float(p["gain"]) != 1.0:
            bits.append("gain x%g" % float(p["gain"]))
        if p.get("clim"):
            bits.append("colour pinned %.3g to %.3g" % tuple(p["clim"][:2]))
        if spec.get("plot") in ("spectrogram", "scalogram"):
            if p.get("fmin") is not None and p.get("fmax") is not None:
                bits.append("%g-%g Hz" % (float(p["fmin"]), float(p["fmax"])))
        ev = p.get("events") or []
        if ev:
            src = p.get("events_source")
            bits.append("%d mark%s%s" % (len(ev), "" if len(ev) == 1 else "s",
                                         (" from " + src) if src else ""))
        return {
            "phrases": bits,
            "fields": {
                "tool": "xplore", "plot": spec.get("plot"),
                "window_s": [t0, t1],
                "filters_hz": {"highpass": p.get("highpass") or 0,
                               "lowpass": p.get("lowpass") or 0,
                               "notch": p.get("notch") or 0},
                "channels_csc": nums, "bad_csc": bad,
                "events": len(ev), "events_source": p.get("events_source"),
                "params": clean_params(p),
                "fs": (sess or {}).get("fs") or prep.get("fs"),
            },
        }

    def numbers(self, spec, prep):
        prep = prep or {}
        win = prep.get("win")
        if win:
            out = {"t": np.linspace(win["t0"], win["t1"], win["n_points"]),
                   "csc": np.array([s["number"] for s in win["series"]])}
            mins = [[np.nan if v is None else v for v in s["min"]]
                    for s in win["series"]]
            maxs = [[np.nan if v is None else v for v in s["max"]]
                    for s in win["series"]]
            out["min_uv"] = np.array(mins, dtype=float)
            out["max_uv"] = np.array(maxs, dtype=float)
            return out
        panel = prep.get("panel")
        if panel and panel.get("image"):
            from .. import compose
            img = compose._decode_data_uri(panel["image"])
            return {"rgb": (np.asarray(img)[..., :3] * 255).astype(np.uint8),
                    "extent": np.array(panel["extent"], dtype=float),
                    "clim": np.array(panel["clim"], dtype=float)}
        return {}


def _row_numbers(prep):
    win = (prep or {}).get("win")
    if win:
        return [int(s["number"]) for s in win["series"]]
    panel = (prep or {}).get("panel") or {}
    return [int(r["number"]) for r in (panel.get("rows") or [])
            if r.get("number") is not None]


def _colorbar(fig, ax, clim, cmap, st):
    """A colour bar beside `ax`, inside the pad layout.py left for it."""
    from matplotlib.colorbar import ColorbarBase
    from matplotlib.colors import Normalize

    from .. import analysis
    fw, fh = fig.get_size_inches()
    pos = ax.get_position()
    pad = 3.0 / 72.0 / fw
    width = 5.0 / 72.0 / fw
    cax = fig.add_axes([pos.x1 + pad, pos.y0, width, pos.height])
    ColorbarBase(cax, cmap=analysis.get_cmap(cmap),
                 norm=Normalize(vmin=float(clim[0]), vmax=float(clim[1])))
    return cax


def _nice(x):
    """1, 2 or 5 times a power of ten, not above x."""
    if not x or x <= 0 or not np.isfinite(x):
        return 1.0
    e = 10 ** np.floor(np.log10(x))
    for m in (5, 2, 1):
        if m * e <= x:
            return float(m * e)
    return float(e)


def _round3(x):
    """Three significant figures, as a number."""
    if not x or not np.isfinite(x):
        return 0.0
    return float("%.3g" % x)


def _say_time(s):
    if s >= 1:
        return "%g s" % s
    if s >= 1e-3:
        return "%g ms" % round(s * 1e3, 6)
    return "%g µs" % round(s * 1e6, 6)


def _say_volt(uv):
    if uv >= 1000:
        return "%g mV" % float("%.3g" % (uv / 1000.0))
    return "%g µV" % float("%.3g" % uv)


register(Xplore())
