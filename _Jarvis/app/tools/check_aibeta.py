# -*- coding: utf-8 -*-
"""The rules AI Beta rests on, checked on data made up for the purpose.

`_dev/aibeta.html` checks the panel. This checks the parts underneath it
that a panel cannot see and that would be silently wrong rather than
loudly broken:

  * which version is the answer -- the last one before Braces that holds
    only DS and Garbage -- and which entries are skipped, and why;
  * one entry per recording, the larger one kept;
  * a Toothy-clock version converted to the recording's own clock, and a
    true-clock one left alone;
  * the per-recording clock correction following a step and refusing to
    guess where the offsets scatter;
  * the counts a threshold produces;
  * training never testing on a mouse it trained on, and finding a signal
    that is there;
  * the sweep's tolerance -- more real spikes allowed to go cleaning more
    garbage and flagging less, at the cost it states, the DS bar fixed;
  * the blend averaging five draws, and saving like any model;
  * the waveform measures reading a width, a lag, a symmetry and noise
    off waveforms built to have them.

    python tools/check_aibeta.py

Writes nothing, starts no server, reads no recording.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

import numpy as np                                       # noqa: E402

from backend import aibeta as AI, eventbank, retime     # noqa: E402

OK, BAD = [], []


def ck(name, good, why=""):
    (OK if good else BAD).append(name)
    print(("  ok   " if good else "  FAIL ") + name
          + (("\n       " + str(why)) if (why and not good) else ""))


class FakeBank:
    """The four things `aibeta.dataset` asks of the Event Bank."""

    def __init__(self, recs):
        self.recs = recs

    def all(self):
        return self.recs

    @staticmethod
    def version_key(ver):
        return eventbank.EventBank.version_key(ver)

    def events_at(self, rec, key):
        ver = eventbank.EventBank.version_at(rec, key)
        names = rec.get("label_names") or {}
        out = []
        for row in ver["snap"]:
            ev = {"start": float(row[0])}
            if len(row) > 1 and row[1]:
                ev["label_id"] = row[1]
                ev["label"] = names.get(row[1], row[1])
            out.append(ev)
        return out, []

    def basis_at(self, rec, v):
        return eventbank.EventBank.basis_at(rec, v)


def ver(v, by_label, snap, aligned=False, vid=None, at=None):
    return {"v": v, "id": vid or ("v%d-x" % v), "by_label": by_label,
            "snap": snap, "aligned": aligned,
            "at": at or "2026-01-01T00:00:%02d" % v,
            "from_v": v - 1 if v else None}


def entry(eid, gid, mouse, versions, pipeline="ETS dentate-spike export",
          project="PTEN"):
    return {"id": eid, "gid": gid, "type": "ds", "project": project,
            "mouse": mouse, "session": 1,
            "session_label": "%s m%d s1" % (project, mouse),
            "source": {"pipeline": pipeline}, "versions": versions,
            "label_names": {"spike": "Dentate Spike", "garbage": "Garbage"}}


# --------------------------------------------------------------------------
print("\nWhich version is the answer")
times = [10.0, 20.0, 30.0, 40.0]
v0 = ver(0, {"unspecified": 4}, [[t] for t in times])
# A first pass that flags one and gets one wrong.
v1 = ver(1, {"spike": 1, "garbage": 2, "flag": 1},
         [[10.0, "spike"], [20.0, "garbage"], [30.0, "flag"],
          [40.0, "garbage"]])
v2 = ver(2, {"spike": 3, "garbage": 1},
         [[10.0, "spike"], [20.0, "garbage"], [30.0, "spike"],
          [40.0, "spike"]])
v3 = ver(3, {"Dentate Spike": 3}, [[10.002, "spike"], [30.001, "spike"],
                                   [40.0, "spike"]], aligned=True)
v4 = ver(4, {"spike": 1, "garbage": 3},
         [[10.0, "spike"], [20.0, "garbage"], [30.0, "garbage"],
          [40.0, "garbage"]])
a = entry("A", "gA", 1, [v0, v1, v2, v3, v4])
b = entry("B", "gB", 2, [ver(0, {"unspecified": 2}, [[1.0], [2.0]])])
h = entry("H", "gH", 3, [v0, v2], pipeline="harness: something")
d1 = entry("D1", "gD", 4, [v0, v2])
d2 = entry("D2", "gD", 4, [ver(0, {"unspecified": 2}, [[1.0], [2.0]]),
                           ver(1, {"spike": 2}, [[1.0, "spike"],
                                                 [2.0, "spike"]])])
g = entry("G", "gG", 6, [v0, ver(1, {"garbage": 4},
                                [[t, "garbage"] for t in times])])
ds = AI.dataset(FakeBank([a, b, h, d1, d2, g]))
by = {e["entry_id"]: e for e in ds["entries"]}
ck("the settled version before Braces is the answer, not a later one",
   by.get("A", {}).get("version_v") == 2,
   by.get("A", {}).get("version_v"))
ck("its labels come through as 1 for DS and 0 for Garbage",
   [e["y"] for e in by["A"]["events"]] == [1, 0, 1, 1],
   [e["y"] for e in by["A"]["events"]])
ck("a first pass is compared with the settled call",
   by["A"]["first_pass"] == {"called": 3, "agree": 2, "flagged": 1,
                             "compared": 4}, by["A"]["first_pass"])
ck("an entry with nothing settled is skipped, with a reason",
   any(s["entry_id"] == "B" and "not finished" in s["why"]
       for s in ds["skipped"]), ds["skipped"])
ck("a harness entry is not learned from", "H" not in by)
av = ver(5, {"spike": 2, "garbage": 2},
         [[10.0, "spike"], [20.0, "garbage"], [30.0, "garbage"],
          [40.0, "spike"]])
av["tag"] = "avery"
ds_av = AI.dataset(FakeBank([entry("V", "gV", 7, [v0, v1, v2, av])]))
ck("a model's version is never the answer, however settled it looks",
   ds_av["entries"] and ds_av["entries"][0]["version_v"] == 2,
   [(e["label"], e["version_v"]) for e in ds_av["entries"]])
pol_p = np.array([0.95, 0.9, 0.85, 0.5, 0.4, 0.2, 0.1, 0.05, 0.02, 0.01])
pol_y = np.array([1, 1, 1, 1, 0, 1, 0, 0, 0, 0])
pol = AI.label_policy(pol_p, pol_y)
labs = list(AI.apply_policy(pol_p, pol))
ck("the sweep's bars sort high to DS and low to Garbage",
   labs[0] == "spike" and labs[-1] == "garbage", labs)
ck("and nothing falls outside the four calls",
   set(labs) <= set(AI.POLICY_LABELS), labs)
rs = np.random.default_rng(3)
big_p = np.r_[rs.uniform(0.0, 0.5, 1000), rs.uniform(0.4, 1.0, 1000)]
big_y = np.r_[np.zeros(1000, int), np.ones(1000, int)]
bp = AI.label_policy(big_p, big_y)
caught = float((big_p[big_y == 0] < bp["t_ds"]).mean())
ck("the DS bar sits above 99% of the garbage",
   abs(caught - 0.99) < 0.005, caught)
pure = bp["held_out"]["garbage"]
ck("Garbage calls are at least nine in ten garbage",
   pure["n"] and pure["n_garbage"] / pure["n"] >= 0.9, pure)
ck("a recording rejected whole is left out, and says so",
   "G" not in by and any(s["entry_id"] == "G"
                         and s["why"].startswith("rejected whole")
                         for s in ds["skipped"]), ds["skipped"])
ck("one entry per recording, the larger kept", "D1" in by and "D2" not in by,
   sorted(by))
ck("the smaller twin is reported as a second entry",
   any(s["entry_id"] == "D2" and s["why"].startswith("a second entry")
       for s in ds["skipped"]), ds["skipped"])
ck("an ETS export with no stamp is read as Toothy's clock",
   by["A"]["basis"] == retime.CONCAT, by["A"]["basis"])
inc = entry("I", "gI", 5, [v0, v2], pipeline="Incisor (dentate spike)")
ck("an Incisor set is on the recording's own clock",
   AI.dataset(FakeBank([inc]))["entries"][0]["basis"] == retime.TRUE)

# --------------------------------------------------------------------------
print("\nA set a person finished after a model's sweep")
t6 = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
pv0 = ver(0, {"unspecified": 6}, [[t] for t in t6])
pv1 = ver(1, {"spike": 1, "garbage": 1, "unspecified": 4},
          [[1.0, "spike"], [2.0, "garbage"], [3.0], [4.0], [5.0], [6.0]])
pav = ver(2, {"spike": 3, "garbage": 2, "flag": 1},
          [[1.0, "spike"], [2.0, "garbage"], [3.0, "spike"],
           [4.0, "garbage"], [5.0, "flag"], [6.0, "spike"]])
pfin = ver(3, {"spike": 3, "garbage": 3},
           [[1.0, "spike"], [2.0, "garbage"], [3.0, "spike"],
            [4.0, "spike"], [5.0, "garbage"], [6.0, "garbage"]])
for how, mark in (("Tooth Fairy's, tagged", {"tag": AI.MODEL_TAG,
                                              "by": AI.MODEL_BY}),
                  ("Tooth Fairy's, by its author alone", {"by": AI.MODEL_BY}),
                  ("an older model's, tagged", {"tag": "avery",
                                                "by": "Avery (AI)"}),
                  ("an older model's, by its author alone",
                   {"by": "Avery (AI)"})):
    e_av = entry("S", "gS", 9, [pv0, pv1, dict(pav, **mark), pfin])
    got_s = AI.dataset(FakeBank([e_av]))["entries"]
    kept = [e["t_bank"] for e in got_s[0]["events"]] if got_s else None
    ck("a call the model made and nobody changed is left out (%s)" % how,
       kept == [1.0, 2.0, 4.0, 5.0, 6.0], kept)
ck("and counted", got_s and got_s[0]["n_model_left_out"] == 1,
   got_s and got_s[0].get("n_model_left_out"))
ck("kept: what a person decided before, what it flagged, what was changed",
   got_s and [e["y"] for e in got_s[0]["events"]] == [1, 0, 1, 0, 0],
   got_s and [e["y"] for e in got_s[0]["events"]])
e_nos = entry("S2", "gS2", 10,
              [pv0, pv1, dict(pav, by=AI.MODEL_BY, snap=None), pfin])
ds_nos = AI.dataset(FakeBank([e_nos]))
ck("without the model's version on this machine, the set is left out, "
   "saying so",
   not ds_nos["entries"] and any("a model swept it" in s["why"]
                                 for s in ds_nos["skipped"]),
   ds_nos["skipped"])
ck("a set no model swept is untouched",
   [e["t_bank"] for e in AI.dataset(FakeBank([entry(
       "S3", "gS3", 11, [pv0, pv1, pfin])]))["entries"][0]["events"]] == t6)
gv0 = ver(0, {"unspecified": 5}, [[t] for t in t6[:5]])
gv1 = ver(1, {"spike": 2, "garbage": 3},
          [[1.0, "spike"], [2.0, "garbage"], [3.0, "garbage"],
           [4.0, "spike"], [5.0, "garbage"]])
# The set made ready for Braces: garbage deleted, and one call changed.
gv2 = ver(2, {"spike": 3}, [[1.0, "spike"], [3.0005, "spike"],
                            [4.0, "spike"]])
got_g = AI.dataset(FakeBank([entry("R", "gR", 12, [gv0, gv1, gv2])]))
eg = got_g["entries"][0] if got_g["entries"] else {}
ck("the DS-only version is still the answer", eg.get("version_v") == 2,
   eg.get("version_v"))
ck("the garbage it deleted comes back as garbage",
   [(e["t_bank"], e["y"]) for e in eg.get("events", [])]
   == [(1.0, 1), (2.0, 0), (3.0005, 1), (4.0, 1), (5.0, 0)],
   [(e["t_bank"], e["y"]) for e in eg.get("events", [])])
ck("a candidate it kept keeps its call, and the count says what came back",
   eg.get("n_garbage_restored") == 2 and eg.get("n_garbage") == 2,
   (eg.get("n_garbage_restored"), eg.get("n_garbage")))
ck("Tooth Fairy is a model a sweep can use",
   "tooth_fairy" in AI.SLOTS and AI.SLOT_NAMES["tooth_fairy"] == "Tooth Fairy")

# --------------------------------------------------------------------------
print("\nThe clock")
report = {"ok": True, "segments": [
    {"concat_t0_s": 0.0, "duration_s": 25.0, "error_ms": 0.0,
     "true_t0_s": 0.0},
    {"concat_t0_s": 25.0, "duration_s": 100.0, "error_ms": 80.0,
     "true_t0_s": 25.08}]}
tt = AI.true_times(by["A"], report)
ck("before the gap a Toothy time is unchanged", tt[0] == 10.0, tt)
ck("after the gap it moves by the gap", abs(tt[2] - 30.08) < 1e-9, tt)
tt_inc = AI.true_times(AI.dataset(FakeBank([inc]))["entries"][0], report)
ck("a true-clock time is never converted", tt_inc[2] == 30.0, tt_inc)

rng = np.random.default_rng(1)
off = np.concatenate([rng.normal(-3, 1, 60), rng.normal(-40, 1, 60)])
corr, ok = AI._running_median(off)
ck("the correction follows a step at a gap",
   abs(corr[10] + 3) < 1.5 and abs(corr[100] + 40) < 1.5,
   (corr[10], corr[100]))
ck("and is trusted there", ok[10] and ok[100])
noise = rng.uniform(-100, 100, 80)
corr2, ok2 = AI._running_median(noise)
ck("scattered offsets are not guessed at", not ok2.any()
   and np.all(corr2 == 0), (ok2.sum(), corr2[:3]))

# --------------------------------------------------------------------------
print("\nCounting at a threshold")
y = np.array([1, 1, 1, 1, 0, 0, 0])
p = np.array([0.9, 0.8, 0.4, 0.1, 0.6, 0.3, 0.05])
m = AI.metrics(y, p, 0.35)
ck("DS kept and flagged", (m["ds_kept"], m["ds_flagged"]) == (3, 1),
   (m["ds_kept"], m["ds_flagged"]))
ck("garbage caught and let through",
   (m["garbage_caught"], m["garbage_through"]) == (2, 1),
   (m["garbage_caught"], m["garbage_through"]))
ck("everything under the bar is a flag, none dropped",
   m["flagged"] == 3 and m["ds_kept"] + m["garbage_through"]
   + m["flagged"] == len(y))
ck("the bar keeps the asked-for share of DS",
   abs(AI._threshold(np.linspace(0, 1, 101), 0.98) - 0.02) < 1e-9)

# --------------------------------------------------------------------------
print("\nTraining never tests on a mouse it trained on")
fams = ["incisor", "shank"]
data = []
rng = np.random.default_rng(7)
for k in range(8):
    n = 120
    yk = (rng.random(n) < 0.75).astype(np.int8)
    f = {fid: np.full((n, len(AI._NAMES[fid])), np.nan, np.float32)
         for fid in AI.FAMILY_IDS}
    # One real signal in one column, plus noise everywhere else.
    f["incisor"][:] = rng.normal(0, 1, f["incisor"].shape)
    f["shank"][:] = rng.normal(0, 1, f["shank"].shape)
    f["incisor"][:, 1] += 2.5 * yk
    feat = {"fam": f, "ok": np.ones(n, bool), "y": yk}
    ent = {"entry_id": "E%d" % k, "label": "PTEN m%d s1" % (k // 2),
           "mouse_key": "PTEN m%d" % (k // 2), "source": "Toothy import"}
    data.append((ent, feat))
res, model, names, thr = AI.train_and_test(data, fams, "hgb")
fold_mice = [set(f["mice"]) for f in res["folds"]]
ck("no mouse is in two test folds",
   sum(len(s) for s in fold_mice) == len(set().union(*fold_mice)),
   fold_mice)
ck("two sessions of one mouse are tested together",
   all(len({r["fold"] for r in res["by_recording"]
            if r["mouse"] == mk}) == 1
       for mk in {r["mouse"] for r in res["by_recording"]}))
ck("a real signal is found on unseen mice",
   (res["pooled"]["auc"] or 0) > 0.85, res["pooled"]["auc"])
ck("it is the input that carries it that it leans on",
   res["leaned_on"][0]["id"] == "incisor", res["leaned_on"])
ck("the saved bar keeps about 98% of DS",
   abs(res["pooled"]["ds_kept_frac"] - AI.KEEP_DS) < 0.05,
   res["pooled"]["ds_kept_frac"])
ck("feature names line up with the inputs",
   len(names) == len(AI._NAMES["incisor"]) + len(AI._NAMES["shank"]))

print("\nRecording context")
fam0 = data[0][1]["fam"]
okm = np.ones(fam0["incisor"].shape[0], bool)
okm[:10] = False
rc = AI.derive_recording(fam0, okm)
ck("one row per event, the same for every event",
   rc.shape[0] == okm.size and np.allclose(rc, rc[0], equal_nan=True))
amp = fam0["incisor"][okm, AI._NAMES["incisor"].index("amp_uv")]
ck("taken over the readable candidates only",
   abs(rc[0, AI._NAMES["recording"].index("rec_amp_uv")]
       - np.median(amp)) < 1e-3)
ck("off by default", not next(f for f in AI.FAMILIES
                              if f["id"] == "recording")["default"])

# --------------------------------------------------------------------------
print("\nHow many real spikes may be called Garbage")
from backend import toothfairy as AV                     # noqa: E402


class FakeRuns:
    def __init__(self, recs):
        self.recs = recs

    def get(self, run_id):
        return self.recs.get(run_id)


tr_ = np.random.default_rng(11)
t_p = np.r_[tr_.beta(2, 5, 1500), tr_.beta(6, 2, 6000)]
t_y = np.r_[np.zeros(1500, int), np.ones(6000, int)]
t_base = AI.label_policy(t_p, t_y, AI.POLICY_PLUS)
t_runs = FakeRuns({"r1": {"results": {"oof": {"p": t_p.tolist(),
                                              "y": t_y.tolist()}}},
                   "old": {"results": {}}})
tab = AV.tolerance_table(t_runs, "r1", t_base)
ck("one row for every tolerance offered",
   [r["ds_loss"] for r in tab] == list(AV.TOLERANCES), tab)
ck("the default is one of them", AV.DEFAULT_TOLERANCE in AV.TOLERANCES)
ck("allowing more spikes to go cleans more garbage",
   all(a["garbage_cleaned"] <= b["garbage_cleaned"]
       for a, b in zip(tab, tab[1:])), [r["garbage_cleaned"] for r in tab])
ck("and leaves fewer candidates flagged for a person",
   all(a["flagged"] >= b["flagged"] for a, b in zip(tab, tab[1:])),
   [r["flagged"] for r in tab])
ck("and costs about the spikes it says it will",
   all(abs(r["ds_called_garbage"] - r["ds_loss"]) < 0.01 for r in tab),
   [(r["ds_loss"], r["ds_called_garbage"]) for r in tab])
ck("the DS bar never moves with it, so garbage into DS does not change",
   len({r["garbage_into_ds"] for r in tab}) == 1,
   [r["garbage_into_ds"] for r in tab])
moved = AV.policy_for(t_runs, "r1", t_base, 0.25)
ck("moving the Garbage bar keeps the DS and review bars",
   moved["t_ds"] == t_base["t_ds"] and moved["t_review"] == t_base["t_review"]
   and moved["t_garbage"] > t_base["t_garbage"], (moved, t_base))
ck("no tolerance asked for is the run's own bars",
   AV.policy_for(t_runs, "r1", t_base, None) is t_base)
ck("a run without held-out scores offers no tolerance",
   AV.tolerance_table(t_runs, "old", t_base) == [])
ck("Tooth Fairy is the only model a sweep can use",
   AI.SLOTS == ("tooth_fairy",)
   and AI.SLOT_NAMES["tooth_fairy"] == "Tooth Fairy")

# --------------------------------------------------------------------------
print("\nEven channels only")
from backend import aibetaphys as PH                      # noqa: E402
lin = {"channels": [{"number": n} for n in range(1, 65)], "probe": "h3",
       "bad": [3, 8, 13], "spacing": None, "session": None}
ev_ = AI.subset_channels(lin, "even")
ck("CSC 2, 4 ... 64 and nothing else",
   [c["number"] for c in ev_["channels"]] == list(range(2, 65, 2)),
   [c["number"] for c in ev_["channels"]][:6])
ck("only the bad channels among them stay bad", ev_["bad"] == [8], ev_["bad"])
ck("read as twice the pitch apart",
   ev_["spacing"] == 2 * AI.dspca.spacing_for("h3"), ev_["spacing"])
ck("all channels is the recording as it was",
   AI.subset_channels(lin, "all") is lin and AI.subset_channels(lin, None) is lin)
col_ = AI.subset_channels(dict(lin, probe="h10d"), "even")
ck("a probe laid out in columns is read whole, and says so",
   len(col_["channels"]) == 64 and not col_.get("subset")
   and "laid out in columns" in (col_.get("subset_note") or ""),
   (len(col_["channels"]), col_.get("subset"), col_.get("subset_note")))
e_k = {"entry_id": "E", "version": 1, "basis": None,
       "events": [{"t_bank": 1.0, "y": 1}]}
ck("a full read keeps the key it always had",
   AI.cache_key(e_k, "h3", None, [3]) == AI.cache_key(e_k, "h3", None, [3], None))
ck("an even read is filed apart",
   AI.cache_key(e_k, "h3", 100.0, [8], "even")
   != AI.cache_key(e_k, "h3", 100.0, [8]))
ck("every contact: the second read's windows as they always were",
   PH._row_windows(1.0) == {"near": 4, "far": 12, "lat": 10,
                            "depth": PH.ALIGN_DEPTH, "img": 8},
   PH._row_windows(1.0))
ck("every other contact: half the rows, the same depth",
   PH._row_windows(0.5) == {"near": 2, "far": 6, "lat": 5,
                            "depth": PH.ALIGN_DEPTH // 2, "img": 4},
   PH._row_windows(0.5))

# --------------------------------------------------------------------------
print("\nThe waveform image at the aligned peak")
blk_ = np.zeros((32, 301))
blk_[20, 140:161] = np.hanning(21)            # a bump on row 20, peak at 150
im3 = PH._wave_image(blk_, 20, 150, 3, 8)
im50 = PH._wave_image(blk_, 20, 150, 50, 8)
ck("17 depths by 13 times whatever the window",
   im3.shape == im50.shape == (PH.IMG_ROWS, PH.IMG_COLS), (im3.shape, im50.shape))
ck("the peak in the middle of the picture",
   np.unravel_index(im3.argmax(), im3.shape) == (8, 6)
   and np.unravel_index(im50.argmax(), im50.shape) == (8, 6),
   (np.unravel_index(im3.argmax(), im3.shape),
    np.unravel_index(im50.argmax(), im50.shape)))
ck("a narrow window sees only the top of it",
   im3[8].min() > 0.75, im3[8].round(2).tolist())
ck("a wide one the whole bump, its columns averaged rather than sampled",
   im50[8, 0] == 0 and im50[8, -1] == 0
   and (im50[8] > 0.05).sum() >= 3
   and abs(im50[8].sum() * (101 / 13.0) - blk_[20].sum()) < 1.0,
   im50[8].round(2).tolist())
ck("every other contact covers the same depth with half the rows",
   np.allclose(PH._wave_image(blk_[::2], 10, 150, 10, 4)[[0, 8, 16]],
               PH._wave_image(blk_, 20, 150, 10, 8)[[0, 8, 16]]))
ck("rows past the end of the probe repeat the last one",
   np.allclose(PH._wave_image(blk_, 0, 150, 10, 8)[:8],
               PH._wave_image(blk_, 0, 150, 10, 8)[8]))
ck("one input per window, 3 to 50 ms",
   [f for f in AI.FAMILY_IDS if f.startswith("wimg")]
   == ["wimg3", "wimg5", "wimg10", "wimg15", "wimg25", "wimg50"]
   and all(len(AI._NAMES[f]) == 221 for f in PH.IMG_IDS))
import tempfile                                           # noqa: E402
tmp_ = os.path.join(tempfile.mkdtemp(), "phys.npz")
PH.save(tmp_, {"ok": np.ones(2, bool), "missed": 0, "has_video": False,
               "n_markers": 0, "fam": {"mua": np.zeros((2, 5))}})
ck("a read from before an input existed is read again for it",
   PH.has(tmp_, ["mua"]) and not PH.has(tmp_, ["mua", "wimg15"])
   and PH.has(tmp_, []))
PH.save(tmp_, {"ok": np.ones(2, bool), "missed": 0, "has_video": False,
               "n_markers": 0, "fam": {"mua": np.zeros((2, 5)),
                                       "wimg15": np.zeros((2, 221))}})
ck("pictures of the current kind are used as they are",
   PH.has(tmp_, ["mua", "wimg15"]))
with np.load(tmp_) as z_:
    np.savez(tmp_[:-4] + "_old.npz", **{k: z_[k] for k in z_.files
                                       if k != "iv"})
ck("pictures from before the current kind are read again",
   not PH.has(tmp_[:-4] + "_old.npz", ["wimg15"])
   and PH.has(tmp_[:-4] + "_old.npz", ["mua"]))
ck("and still loads for a run that does not want it",
   "mua" in (PH.load(tmp_[:-4] + "_old.npz") or {}).get("fam", {}))

# --------------------------------------------------------------------------
print("\nThe snapshots through other filters")
ck("six filters, three snapshots each",
   [f for f, _b in PH.FILTERS] == ["notch", "1_20", "1_100", "5_50",
                                    "10_40", "5_100"]
   and len(PH.FILT_IDS) == 18
   and all(f in AI.FAMILY_IDS for f in PH.FILT_IDS))
ck("pictures 17 by 13, the trace +-50 ms at 2 ms",
   len(AI._NAMES["fwhole_1_20"]) == len(AI._NAMES["fthin_10_40"]) == 221
   and len(AI._NAMES["ftrace_notch"]) == 51)
ck("listed with the pictures, off by default",
   all(f.get("group") == "pictures" and not f["default"]
       for f in AI.FAMILIES if f["id"] in PH.FILT_IDS))
tt_ = np.arange(301)
slow_ = np.tile(np.sin(2 * np.pi * 10 * tt_ / 1000.0), (32, 1)) \
    * np.hanning(32)[:, None]
st_f = {"filt": {f: (slow_ + 7.0).astype(np.float32) if f == "notch"
                 else slow_.astype(np.float32)
                 for f, _b in PH.FILTERS if f != "5_100"}}
spec_ = {"band": (5.0, 100.0), "line_hz": 60.0, "line_q": 30.0,
         "lfp_fs": 1000.0, "spacing_um": 100.0, "csd_smooth": True}
fam_f = {k: np.full((2, len(AI._NAMES[k])), np.nan) for k in PH.FILT_IDS}
PH._filtered_snapshots(st_f, slow_, 16, 150, 1000.0, spec_,
                       PH._row_windows(0.5), fam_f, 0)
ck("every snapshot filled, scaled so its largest value is 1",
   all(np.isfinite(fam_f[k][0]).all()
       and abs(np.abs(fam_f[k][0]).max() - 1) < 1e-6 for k in PH.FILT_IDS))
ck("the notch-only snapshot has each row's offset taken off",
   np.allclose(fam_f["ftrace_notch"][0], fam_f["ftrace_1_20"][0], atol=0.05))
ck("the 5-100 Hz ones are the band the read already holds",
   np.allclose(fam_f["fthin_5_100"][0],
               PH._unit(PH._wave_image(slow_, 16, 150, 25, 4)).ravel()))
fam_n = {k: np.full((1, len(AI._NAMES[k])), np.nan) for k in PH.FILT_IDS}
PH._filtered_snapshots({"filt": {}}, slow_, 16, 150, 1000.0, spec_,
                       PH._row_windows(0.5), fam_n, 0)
ck("nothing is taken when the filters were not asked for",
   all(np.isnan(fam_n[k]).all() for k in PH.FILT_IDS))
ck("a model's inputs name the filters to run, and only those",
   PH.filters_for(["mua", "fwhole_10_40", "ftrace_10_40"]) == {"10_40"}
   and PH.filters_for(["mua"]) == set())
fam_o = {k: np.full((1, len(AI._NAMES[k])), np.nan) for k in PH.FILT_IDS}
PH._filtered_snapshots(st_f, slow_, 16, 150, 1000.0, spec_,
                       PH._row_windows(0.5), fam_o, 0, {"10_40"})
ck("and only theirs are taken",
   all(np.isfinite(fam_o[k]).all() == k.endswith("_10_40")
       for k in PH.FILT_IDS))

# --------------------------------------------------------------------------
print("\nX-ray at the real peaks near the stamp")
tq = np.arange(301)
rng_x = np.random.default_rng(8)
bt_ = (np.exp(-0.5 * ((tq - 150) / 4.0) ** 2) * 10
       + np.exp(-0.5 * ((tq - 190) / 4.0) ** 2) * 4
       + 0.3 * np.abs(np.sin(tq / 3.0)) + 0.05 * rng_x.standard_normal(301))
base_, sd_ = float(np.median(bt_)), float(np.median(np.abs(bt_ - np.median(bt_)))) * 1.4826
got_pk = PH._peaks(bt_, 50, 251, 12, base_, sd_)
ck("the real peaks only, largest first: ripples are not peaks",
   [abs(q - 150) <= 1 for q in got_pk[:1]] == [True]
   and len(got_pk) == 2 and abs(got_pk[1] - 190) <= 1, got_pk)
ck("a quiet stretch has none",
   PH._peaks(0.3 * np.abs(np.sin(tq / 3.0)), 50, 251, 12, base_, sd_) == [])
store_x, have_x, bts = {}, [], []
for k in range(12):
    vb = 0.5 * rng_x.standard_normal((32, 301))
    prof_x = np.exp(-0.5 * ((np.arange(32) - 14) / 2.0) ** 2)
    for q, amp in ((150, 100.0), (190, 40.0)):
        vb += amp * prof_x[:, None] * np.exp(-0.5 * ((tq - q) / 6.0) ** 2)[None, :]
    store_x[k] = {"filt": {"10_40": vb.astype(np.float32)}}
    have_x.append(k)
    bts.append(bt_)
fam_x = {"xray5": np.full((12, len(AI._NAMES["xray5"])), np.nan)}
PH._xray(store_x, have_x, np.zeros(12), [150] * 12, bts, 1000.0, 150,
         {"band": (5.0, 100.0)}, PH._row_windows(0.5), fam_x, 100.0)
row_x, per_x = fam_x["xray5"][0], len(AI._NAMES["xray5"]) // len(PH.XR_SLOTS)
ck("the assigned peak, then the two real ones, then nothing",
   np.isfinite(row_x[:3 * per_x]).all() and np.isnan(row_x[3 * per_x:]).all(),
   [bool(np.isfinite(row_x[k * per_x])) for k in range(len(PH.XR_SLOTS))])
ck("each says when it is and how tall",
   row_x[per_x] == 0.0 and abs(row_x[2 * per_x] - 40.0) < 1.5
   and abs(row_x[2 * per_x + 1] - 0.4) < 0.05,
   (row_x[per_x], row_x[2 * per_x], row_x[2 * per_x + 1]))
ck("X-ray at the top five peaks is an input, off by default, through 10-40 Hz",
   "xray5" in AI.FAMILY_IDS and len(AI._NAMES["xray5"]) == 168
   and PH.filters_for(["xray5"]) == {"10_40"}
   and not next(f for f in AI.FAMILIES if f["id"] == "xray5")["default"])

# --------------------------------------------------------------------------
print("\nThe blend")
import io                                                 # noqa: E402
import joblib                                             # noqa: E402
bx = np.random.default_rng(4).normal(size=(800, 6))
by_ = (bx[:, 0] + 0.6 * np.random.default_rng(5).normal(size=800) > 1.0)
by_ = by_.astype(int)
bm = AI._fit("blend", bx, by_, 0)
mean_ = np.mean([m.predict_proba(bx)[:, 1] for m in bm.fitted], axis=0)
ck("a model to choose", "blend" in AI.MODEL_IDS)
ck("five sets of boosted trees, each its own draw",
   len(bm.fitted) == len(AI.BLEND_MEMBERS) == 5
   and len({m.random_state for m in bm.fitted}) == 5,
   [getattr(m, "random_state", None) for m in bm.fitted])
ck("its score is their average", np.allclose(AI._proba(bm, bx), mean_))
buf = io.BytesIO()
joblib.dump(bm, buf)
buf.seek(0)
ck("it is saved and loaded like any other model",
   np.allclose(joblib.load(buf).predict_proba(bx), bm.predict_proba(bx)))

# --------------------------------------------------------------------------
print("\nThe waveform measures")
from backend import aiwave as WB                          # noqa: E402
step = AI.WAVE_STEP_MS
n_w = len(AI._NAMES["waves"]) - AI.PROFILE_ROWS
half = n_w // 2
t_ms = (np.arange(half) - half // 2) * step


def bump(at_ms=0.0, sd_ms=5.0, decay_ms=None):
    right = decay_ms or sd_ms
    s = np.where(t_ms < at_ms, sd_ms, right)
    return np.exp(-0.5 * ((t_ms - at_ms) / s) ** 2)


def row(w, c=None, prof=None):
    c = bump() if c is None else c
    prof = np.r_[np.linspace(-0.3, 1, 20), np.linspace(1, 0.2, 12)] \
        if prof is None else prof
    return np.r_[w, c, prof]


ix = {n: k for k, n in enumerate(WB.NAMES)}
clean = bump()
jag = clean + 0.15 * np.random.default_rng(5).standard_normal(half)
late = bump(at_ms=6.0)
skew_ = bump(sd_ms=3.0, decay_ms=10.0)
fam_w = {"waves": np.vstack([row(clean), row(jag), row(late), row(skew_),
                             row(clean, c=bump(at_ms=4.0)), row(clean)])}
okw = np.array([True, True, True, True, True, False])
wb = AI.derive_wavebits(fam_w, okw)
ck("twenty-five of them", len(WB.NAMES) == 25 and wb.shape == (6, 25),
   wb.shape)
ck("in the run's inputs, after everything already there",
   AI.FAMILY_IDS[-1] == "wavebits" and "wavebits" in AI.DERIVED
   and AI.feature_names(["wavebits"]) == WB.NAMES)
ck("off by default", not next(f for f in AI.FAMILIES
                              if f["id"] == "wavebits")["default"])
ck("a candidate that could not be read gets none", np.isnan(wb[5]).all())
ck("a clean spike peaks on its stamp", wb[0, ix["wb_peak_ms"]] == 0.0,
   wb[0, ix["wb_peak_ms"]])
fw = 2.0 * np.sqrt(2.0 * np.log(2.0)) * 5.0
ck("its width at half height is the width it has",
   abs(wb[0, ix["wb_fwhm_ms"]] - fw) < 0.5, (wb[0, ix["wb_fwhm_ms"]], fw))
ck("and it is symmetric", wb[0, ix["wb_symmetry"]] > 0.99,
   wb[0, ix["wb_symmetry"]])
ck("one peak, nothing beside it",
   wb[0, ix["wb_n_peaks"]] == 1 and wb[0, ix["wb_second_peak"]] == 0,
   (wb[0, ix["wb_n_peaks"]], wb[0, ix["wb_second_peak"]]))
ck("a late one peaks late", wb[2, ix["wb_peak_ms"]] == 6.0,
   wb[2, ix["wb_peak_ms"]])
ck("noise reads as jagged and high in frequency",
   wb[1, ix["wb_jagged"]] > 2 * wb[0, ix["wb_jagged"]]
   and wb[1, ix["wb_hf_frac"]] > wb[0, ix["wb_hf_frac"]],
   (wb[:2, ix["wb_jagged"]].tolist(), wb[:2, ix["wb_hf_frac"]].tolist()))
ck("fast up and slow down reads as such",
   wb[3, ix["wb_rise_ms"]] < wb[3, ix["wb_decay_ms"]]
   and wb[3, ix["wb_symmetry"]] < wb[0, ix["wb_symmetry"]],
   wb[3, [ix["wb_rise_ms"], ix["wb_decay_ms"], ix["wb_symmetry"]]].tolist())
ck("a CSD peaking 4 ms after the trace is 4 ms late",
   wb[4, ix["wb_csd_lag_ms"]] == 4.0 and wb[0, ix["wb_csd_lag_ms"]] == 0.0,
   (wb[4, ix["wb_csd_lag_ms"]], wb[0, ix["wb_csd_lag_ms"]]))
ck("the depth profile's one sign change is counted",
   wb[0, ix["wb_profile_flips"]] == 1, wb[0, ix["wb_profile_flips"]])

print("\n%d ok, %d failed" % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
