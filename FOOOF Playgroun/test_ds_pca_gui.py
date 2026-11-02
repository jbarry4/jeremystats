"""Exercise the GUI's interactive paths without a window.

The drag and the click are the two things a headless render cannot reach, so
they are driven here directly: synthetic mouse events through the same
callbacks matplotlib would call.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import numpy as np                                               # noqa: E402

sys.path.insert(0, r"C:\Users\Z390\Desktop\jeremystats\FOOOF Playgroun")
sys.argv = ["ds_pca_gui.py"]
import ds_pca_gui as G                                           # noqa: E402

FOLDER = r"D:/PTEN/PTEN/M1_Pten/M1ptens8oct4/2023-10-05_14-09-57"
BANK = os.path.join(G._HERE, "event-bank-M1ptens8oct4-v4.csv")

a = G.Opts(folder=FOLDER, bank=BANK, label="spike", n_events=0,
           refine="nearest", band=(5.0, 100.0), window_ms=100.0,
           surround_ms=50.0, channels="", spacing=30.0, lfp_fs=1000.0,
           pad=0.5, no_invert=False, cond=0.3, f_order=3, f_sigma=1.0,
           no_vaknin=False, h_power=1, csd_bad_x=4.0, csd_span=16, seed=0,
           refresh=False, line=0.0, save=None)

got = G.load_everything(a)
nums, n_t = got["nums"], got["sur"]["raw"].shape[2]
chans = [{"number": int(n)} for n in nums]
state = {
    "args": a, "rows": got["rows"], "nums": nums, "chans": chans,
    "bad0": got["bad"], "sur": got["sur"],
    "session_label": got["session_label"], "mains_uv": got["mains_uv"],
    "wideband_uv": got["wideband_uv"], "notch": True, "screen": True,
    "nclasses": 2, "picked": None, "gain": 4.0,
    "guides": [], "guide_artists": [], "manual_bad": {}, "flip": False,
    "rule": "sources",
    "tw": np.linspace(-a.surround_ms, a.surround_ms, n_t),
    "centre_i": n_t // 2,
}
state["t0"], state["t1"] = state["centre_i"], state["centre_i"] + 1
state["sel"] = G.ds_pca.depth_band(got["sur"]["notch"], a, chans, got["bad"])
fig = G.build(state)

FAIL = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAIL.append(name)


class Ev:
    def __init__(self, x, y):
        self.xdata, self.ydata = x, y


sel_cb = state["selector"].onselect

# --- a drag: 24 ms of time, CSC26..36 ------------------------------------
sel_cb(Ev(-8.0, 26.0), Ev(16.0, 36.0))
tw = state["tw"]
check("drag sets the time window",
      abs(tw[state["t0"]] - (-8.0)) < 1.1 and
      abs(tw[state["t1"] - 1] - 16.0) < 1.1,
      "%.0f..%.0f ms, %d samples"
      % (tw[state["t0"]], tw[state["t1"] - 1], state["t1"] - state["t0"]))
check("drag sets the contact band",
      nums[state["sel"][0]] == 26 and nums[state["sel"][-1]] == 36,
      "CSC%d-%d" % (nums[state["sel"][0]], nums[state["sel"][-1]]))
res = state["res"]
check("features are depth x time, flattened",
      res["n_features"] == len(state["sel"]) * (state["t1"] - state["t0"]),
      "%d = %d contacts x %d samples"
      % (res["n_features"], len(state["sel"]), state["t1"] - state["t0"]))
check("every event still labelled", res["types"].size == len(got["rows"]))

# --- a degenerate drag: fewer than three contacts -------------------------
sel_cb(Ev(0.0, 30.0), Ev(0.0, 31.0))
check("a too-thin drag is widened to three contacts (a CSD needs three)",
      len(state["sel"]) >= 3, "%d contacts" % len(state["sel"]))
check("a zero-width drag still gives one sample",
      state["t1"] - state["t0"] >= 1)

# --- a drag off the ends --------------------------------------------------
sel_cb(Ev(-90.0, -5.0), Ev(90.0, 200.0))
check("a drag past the edges is clipped to the probe and the window",
      state["sel"][0] >= 0 and state["sel"][-1] < len(nums)
      and 0 <= state["t0"] < state["t1"] <= n_t,
      "CSC%d-%d, samples %d..%d" % (nums[state["sel"][0]],
                                    nums[state["sel"][-1]],
                                    state["t0"], state["t1"]))

# --- clicking a dot -------------------------------------------------------
sel_cb(Ev(-8.0, 26.0), Ev(16.0, 36.0))
art = state["pick_artists"][0]


class Pick:
    def __init__(self, artist, ind):
        self.artist, self.ind = artist, ind


handlers = [f for f in fig.canvas.callbacks.callbacks.get("pick_event", {}).values()]
cb = handlers[0]() if handlers else None
cb(Pick(art, [0]))
check("clicking a dot selects that event",
      state["picked"] == int(art._event_rows[0]),
      "event index %s" % state["picked"])
fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "gui_picked.png"), dpi=110)
check("the picked-event view renders", True)

# --- the checkboxes and the class slider ---------------------------------
for lbl in ("60 Hz notch", "CSD screen"):
    before = state["notch"] if lbl == "60 Hz notch" else state["screen"]
    state["_widgets"][1].set_active(
        ["60 Hz notch", "CSD screen"].index(lbl))
    after = state["notch"] if lbl == "60 Hz notch" else state["screen"]
    check("checkbox %r toggles and redraws" % lbl, before != after)
state["_widgets"][0].set_val(4)
check("class slider reaches 4 classes",
      state["res"]["k"] == 4 and set(state["res"]["types"]) <= {1, 2, 3, 4},
      "classes present: %s" % sorted(set(state["res"]["types"])))

# ===================== navigation and picture consistency ================
state["_widgets"][0].set_val(2)
sel_cb(Ev(-8.0, 26.0), Ev(16.0, 36.0))
G.draw(state, state["res"])

n_ev = len(state["rows"])
state["picked"] = None
state["step"](+1)
check("next from the average lands on the first spike", state["picked"] == 0)
state["step"](+1)
check("next steps forward", state["picked"] == 1)
state["step"](-1)
state["step"](-1)
check("prev wraps at the start", state["picked"] == n_ev - 1,
      "index %d of %d" % (state["picked"], n_ev))
state["step"](+1)
check("next wraps at the end", state["picked"] == 0)

seen = set()
for _ in range(n_ev):
    state["step"](+1)
    seen.add(state["picked"])
check("stepping visits every spike exactly once per lap", len(seen) == n_ev,
      "%d of %d" % (len(seen), n_ev))

kcb = state["on_key"]


class Key:
    def __init__(self, key):
        self.key = key


before = state["picked"]
kcb(Key("right"))
check("right arrow steps forward", state["picked"] == (before + 1) % n_ev)
kcb(Key("left"))
check("left arrow steps back", state["picked"] == before)
kcb(Key("escape"))
check("escape returns to the average", state["picked"] is None)

# the pictures must all come off the band-limited CSD now
res = state["res"]
sel, t0, t1 = state["sel"], state["t0"], state["t1"]
expect = res["disp"][:, sel, t0:t1].mean(axis=2)
check("class-average profile is the 5-100 Hz CSD, same as the rasters",
      np.allclose(res["prof"], expect, atol=1e-9))
r1 = np.where(res["types"] == 1)[0]
r2 = np.where(res["types"] == 2)[0]
if r1.size and r2.size:
    # The invariant is about the ACTIVE rule's landmark, not about argmin:
    # ordering by source peaks or by tort's anchored sink can put DS1's
    # plain argmin below DS2's and still be right.
    d1, d2 = res["decide"][0], res["decide"][1]
    s1, s2 = d1["row"], d2["row"]
    check("DS1 holds the shallower landmark under the active rule",
          s1 <= s2, "rule=%s, rows %d vs %d" % (state["rule"], s1, s2))
    for rule in ("tort", "sink", "sources"):
        state["rule"] = rule
        state["res"] = G.recompute(state)
        dd = [d for d in state["res"]["decide"] if d.get("n")]
        rows_ = [d["row"] for d in dd]
        check("rule %-8s orders DS1 shallowest" % rule,
              rows_ == sorted(rows_),
              "rows " + str(rows_) + "  sinks " + str([d["csc"] for d in dd]))
    state["rule"] = "sources"
    state["res"] = G.recompute(state)
    # Under the sink rule the profile landmark IS the raster argmin; the
    # other two rules use a different landmark on purpose, so only this one
    # is comparable.
    state["rule"] = "sink"
    state["res"] = G.recompute(state)
    rz = state["res"]
    q1 = np.where(rz["types"] == 1)[0]
    m1 = rz["disp"][q1].mean(axis=0)[sel, :]
    k1 = int(np.argmin(m1[:, t0:t1].mean(axis=1)))
    check("under the sink rule, the profile landmark is the raster argmin",
          k1 == rz["decide"][0]["row"],
          "row %d vs %d" % (k1, rz["decide"][0]["row"]))

# ===================== depth guides =====================================
state["clear_guides"](None)
check("start with no guides", state["guides"] == [])

state["on_submit"]("30 hilus")
state["on_submit"]("35 granule")
check("typed guides are added, position then name",
      [(g["csc"], g["label"]) for g in state["guides"]]
      == [(30, "hilus"), (35, "granule")],
      str(state["guides"]))

state["on_submit"]("27")
check("a bare number adds an unlabelled guide",
      any(g["csc"] == 27 and g["label"] == "" for g in state["guides"]))
check("guides stay sorted by depth",
      [g["csc"] for g in state["guides"]] == sorted(
          g["csc"] for g in state["guides"]))

state["on_submit"]("30 hilus")
check("re-submitting the same depth removes it (same gesture both ways)",
      not any(g["csc"] == 30 for g in state["guides"]))
state["on_submit"]("30 hilus")


class Click:
    def __init__(self, ax, y, button=3):
        self.inaxes, self.ydata, self.button = ax, y, button
        self.xdata = 0.0


G_ = state["_widgets"][9]
G_.set_val("CA1")
state["on_click"](Click(state["axes"]["csd1"], 22.4))
check("right-click on a class-average panel adds a guide there",
      any(g["csc"] == 22 and g["label"] == "CA1" for g in state["guides"]),
      str([(g["csc"], g["label"]) for g in state["guides"]]))
state["on_click"](Click(state["axes"]["csd1"], 22.2))
check("right-clicking it again takes it off",
      not any(g["csc"] == 22 for g in state["guides"]))

state["on_click"](Click(state["axes"]["space_off"], 0.5))
n_before = len(state["guides"])
check("right-click on the PCA scatter does nothing (not a depth axis)",
      len(state["guides"]) == n_before)
state["on_click"](Click(state["axes"]["csd"], 40.0, button=1))
check("left-click does not add a guide (that gesture is the box)",
      not any(g["csc"] == 40 for g in state["guides"]))

G_.set_val("")
while len(state["guides"]) < 10:
    nxt = max(g["csc"] for g in state["guides"]) + 2
    state["on_submit"]("%d layer%d" % (nxt, nxt))
check("ten guides fit", len(state["guides"]) == 10)
state["on_submit"]("61 eleventh")
check("the eleventh is refused, with a message",
      len(state["guides"]) == 10
      and "limit" in state["guide_note"].get_text(),
      state["guide_note"].get_text())

# they must be on the individual spike AND on the averages
def n_guide_lines(ax):
    return sum(1 for ln in ax.lines
               if getattr(ln, "_guide", False) or
               (len(ln.get_ydata()) == 2
                and ln.get_ydata()[0] == ln.get_ydata()[1]
                and ln.get_ydata()[0] in [g["csc"] for g in state["guides"]]))


state["picked"] = 3
G.draw(state, state["res"])
per_panel = {k: n_guide_lines(state["axes"][k])
             for k in ("volt", "csd", "csd1", "csd2", "prof_off")}
check("guides drawn on an individual spike and on both averages",
      all(v >= 10 for v in per_panel.values()), str(per_panel))

state["picked"] = None
G.draw(state, state["res"])
per_panel2 = {k: n_guide_lines(state["axes"][k])
              for k in ("volt", "csd", "csd1", "csd2", "prof_off")}
check("the same guides survive the switch back to the average",
      per_panel2 == per_panel, str(per_panel2))

for _ in range(6):
    G.draw(state, state["res"])
check("redrawing does not stack guides on the uncleared raster",
      n_guide_lines(state["axes"]["csd"]) == 10,
      "%d lines" % n_guide_lines(state["axes"]["csd"]))

check("guides persist to disk",
      len(G.load_guides(state["args"])) == 10)
fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "gui_guides.png"), dpi=110)
state["clear_guides"](None)
check("clear empties them", state["guides"] == []
      and G.load_guides(state["args"]) == [])

# ===================== the sink-gap separation floor =====================
_mu = np.zeros(30)
_mu[10] = -1.0; _mu[12] = -0.9; _mu[20] = -0.5
_mu[5] = 0.4; _mu[16] = 0.6; _mu[25] = 0.3
check("min_sep=2 allows the 2-apart pair", G.two_sinks(_mu, 2) == (10, 12))
check("min_sep=5 rejects it and takes the far sink",
      G.two_sinks(_mu, 5) == (10, 20), str(G.two_sinks(_mu, 5)))
check("min_sep past every candidate collapses to one sink",
      G.two_sinks(_mu, 12) == (10, 10), str(G.two_sinks(_mu, 12)))
check("the default floor is MIN_SINK_SEP",
      G.two_sinks(_mu) == G.two_sinks(_mu, G.MIN_SINK_SEP))
_blk = np.repeat(_mu[None, :, None], 4, axis=0)
check("the gap feature honours the floor",
      float(G.sink_gap_feature(_blk, 1.0, 12)[0, 0]) == 0.0
      and float(G.sink_gap_feature(_blk, 1.0, 2)[0, 0]) > 0.0)

print("")
print("%d failed" % len(FAIL))
sys.exit(1 if FAIL else 0)
