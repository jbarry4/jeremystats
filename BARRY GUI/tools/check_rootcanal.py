# -*- coding: utf-8 -*-
"""Root Canal's backend, checked without a browser.

What the panel's harness cannot reach, or should not: the arithmetic on
events whose answers are known in advance, the naming rule, the overrides
rebuilding from their parameters alone, the picture gate, and banking --
which writes versions, and so is done here into a THROWAWAY bank in a temp
folder rather than into GUI_logs, where a check run per commit would mint a
version per run forever.

  1. SYNTHETIC EVENTS WITH KNOWN ANSWERS. A fake 30 kHz recording, six
     contacts, white noise at 5 uV:
       * "DS" events, a Gaussian of known FWHM (20 ms) and height (800 uV);
       * "IED" events, a narrower, larger Gaussian with a 700 Hz, 100 uV burst
         across the +-25 ms event window, whose power against the noise is
         worked out analytically (about +37.8 dB) rather than read off
         the code under test;
       * two events that hold their level past the stamp -- to +56 ms and
         to +95 ms -- so a half-amplitude crossing lies past v1's +-50 ms
         search. At 50 both are unresolved (NaN, never the window edge) and
         are ASSIGNED on the two axes they have, flagged `partial`. At an
         80 ms search the first resolves and is flagged `wide`; the second
         is still partial;
       * and, cut into a copy of the read, one flat event with no amplitude
         and no half-width, which has one axis and stays unclassified;
       * a contact marked bad that carries a giant artifact on every event,
         which must never be picked for amplitude or for power.
     Read through `rootcanal.read` (the real decimation, the real PSDs), then
     fit.
  2. The naming rule, the flips, the dragged centres, and a fit rebuilt from
     nothing but the `params` a fit returned.
  3. The picture gate, the version tag, and the routes: fit, event, commit
     (DS vN+1 + an IED entry), an idempotent re-commit, a commit after a
     flip, candidates -- all against the throwaway bank, through Flask's test
     client, with the recording reads pointed at the fake one.
  4. Stop landing: a read inside a job, cancelled mid-recording, ends
     `canceled` with channels still unread; a batch cancelled the same way
     marks its member `stopped`, not `error`.
  5. One real read of 46fd29a77cc7 (PTEN m13 s2), from the cache if it is
     there and off the disk if not, and its counts. `--no-real` skips it;
     `--fresh` reads it again even when cached. The real read is never
     banked.

    python tools/check_rootcanal.py [--no-real] [--fresh]

Writes into a temp folder only, plus -- for the real read, and only when it
is not already cached -- the read's .npz under GUI_logs/.cache, which git
ignores. It checks at the end that the Event Bank on disk is as it found it.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

import numpy as np                                       # noqa: E402

OK, BAD = [], []


def ck(name, good, why=""):
    (OK if good else BAD).append(name)
    print(("  ok   " if good else "  FAIL ") + name
          + (("\n       " + str(why)) if (why and not good) else ""))


def head(title):
    print("")
    print(title)
    print("-" * 66)


PNG1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDw"
    "AEhQGAhKmMIQAAAABJRU5ErkJggg==")
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG1).decode()


def _bank_status():
    """What git says about the Event Bank on disk, to compare at the end."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", "GUI_logs/event_bank",
             "GUI_logs/rootcanal", "GUI_logs/artifacts"],
            cwd=APP, capture_output=True, text=True, timeout=60)
        return out.stdout
    except Exception as exc:                             # noqa: BLE001
        return "git status failed: %s" % exc


# --------------------------------------------------------------------------
# The fake recording
# --------------------------------------------------------------------------
FS = 30000.0
DUR_S = 44.0
NUMS = [1, 2, 3, 4, 5, 6]
MAX_CH = 3                 # where every event is largest
BAD_CH = 6                 # marked bad, and carrying an artifact
NOISE_UV = 5.0
DS_AMP, DS_FWHM = 800.0, 20.0
IED_AMP, IED_FWHM = 1500.0, 10.0
BURST_HZ, BURST_UV = 700.0, 100.0
PLATEAU_MS = (-2.0, 56.0)  # level held past +50 ms: resolves at 80
LONG_MS = (-2.0, 95.0)     # held past +80 ms: unresolved at 50 and at 80
WIDER_MS = 80.0            # the widened search the checks use


def plateau(tt_s, lo_ms=PLATEAU_MS[0], hi_ms=PLATEAU_MS[1], edge_ms=1.5):
    """A flat-topped deflection with smooth edges, 0 outside, 1 on top.

    Why a plateau and not a wide Gaussian: v1's baseline is the median of
    the 30-60 ms flanks, so a wide Gaussian lifts its own baseline and its
    half-level is crossed early -- measured, a 150 ms Gaussian came back
    "resolved" at 62 ms. A level held on one side past +50 ms while the
    other flank is quiet keeps the baseline low and genuinely has no
    crossing in the search.
    """
    e = edge_ms / 1000.0
    return 0.5 * (np.tanh((tt_s - lo_ms / 1000.0) / e)
                  - np.tanh((tt_s - hi_ms / 1000.0) / e))


def _expected_burst_db():
    """10 log10(burst power / noise power in the band), from first principles.

    A sinusoid of amplitude A carries A^2/2. White noise of SD s at 30 kHz,
    anti-aliased and decimated, has a one-sided density of s^2 / (30000/2)
    per Hz, so over the 500 Hz of 500-1000 Hz it is 500 s^2 / 15000.
    """
    sig = BURST_UV ** 2 / 2.0
    noise = NOISE_UV ** 2 * 500.0 / (FS / 2.0)
    return 10.0 * np.log10(sig / noise)


def build_recording(seed=7):
    rng = np.random.default_rng(seed)
    n = int(DUR_S * FS)
    t = np.arange(n) / FS
    data = {c: (rng.standard_normal(n) * NOISE_UV).astype(np.float64)
            for c in NUMS}
    stamps, kinds = [], []
    times = list(np.arange(2.0, 40.0, 2.0)) + [40.0]     # 20 events
    for k, tc in enumerate(times):
        kind = "ied" if k % 2 else "ds"
        if k == 18:
            kind = "plateau"
        elif k == 19:
            kind = "long"
        amp, fwhm = {"ds": (DS_AMP, DS_FWHM), "ied": (IED_AMP, IED_FWHM),
                     "plateau": (DS_AMP, None),
                     "long": (DS_AMP, None)}[kind]
        lo, hi = int((tc - 0.6) * FS), int((tc + 0.6) * FS)
        tt = t[lo:hi] - tc
        if kind == "plateau":
            g = -amp * plateau(tt)
        elif kind == "long":
            g = -amp * plateau(tt, *LONG_MS)
        else:
            sd = fwhm / 1000.0 / 2.3548
            g = -amp * np.exp(-0.5 * (tt / sd) ** 2)   # negative, like a DS
        for c in NUMS:
            scale = {MAX_CH: 1.0, MAX_CH - 1: 0.5, MAX_CH + 1: 0.5}.get(c, 0.2)
            data[c][lo:hi] += scale * g
        if kind == "ied":
            win = np.abs(tt) <= 0.0255
            data[MAX_CH][lo:hi][win] += BURST_UV * np.sin(
                2 * np.pi * BURST_HZ * tt[win])
        # The bad contact: a huge spike and a huge burst, on every event.
        # If anything picks it, the checks below will say so.
        win = np.abs(tt) <= 0.0255
        data[BAD_CH][lo:hi][win] += 5000.0 * np.sin(2 * np.pi * 900.0 * tt[win])
        stamps.append(float(tc))
        kinds.append(kind)
    return data, stamps, kinds


class FakeRecording:
    """Stands in for `csc._read_channel_window` over the arrays above."""

    def __init__(self, data, delay=0.0):
        self.data = data
        self.delay = delay
        self.calls = 0

    def __call__(self, session, ch, t0, t1):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        x = self.data[int(ch["number"])]
        i0 = max(0, int(np.floor(t0 * FS)))
        i1 = min(x.size, max(i0, int(np.ceil(t1 * FS))))
        return x[i0:i1].astype(np.float32), i0 / FS, FS


def fake_session():
    return {"source": "fake", "path": "fake://rootcanal-check", "fs": FS,
            "invert": True, "name": "fake",
            "channels": [{"number": n, "label": "CSC%d" % n, "bad": False}
                         for n in NUMS]}


def fake_channels(bad=True):
    return [{"number": n, "label": "CSC%d" % n,
             "bad": bool(bad and n == BAD_CH)} for n in NUMS]


# --------------------------------------------------------------------------
def main():
    real = "--no-real" not in sys.argv
    fresh = "--fresh" in sys.argv
    before = _bank_status()

    from backend import app as A
    from backend import cfc as cfcmod, csc, eventbank, rootcanal as rc
    from backend import store as storemod, toolresults
    # Synthetic timings must not teach this machine's rate table anything.
    cfcmod._RATES_PATH = None

    tmp = tempfile.mkdtemp(prefix="rootcanal_check_")
    data, stamp_t, kinds = build_recording()
    fake = FakeRecording(data)
    real_reader = csc._read_channel_window
    saved = {k: getattr(A, k) for k in (
        "BANK", "ROOTCANAL", "STORE", "save_output", "_braces_session",
        "_braces_channels", "_stored_for", "ARTIFACTS")}
    saved_screen = A.bracesmod.screen
    try:
        csc._read_channel_window = fake
        _synthetic(A, rc, cfcmod, stamp_t, kinds)
        _routes(A, rc, cfcmod, eventbank, storemod, toolresults, tmp,
                stamp_t, kinds, fake)
        _filter_choices()
        _k_and_margins_core()
        _pool_gmm_agreement()
        _pool_synthetic(A)
        _pool_routes(A, tmp, fake)
    finally:
        csc._read_channel_window = real_reader
        for k, v in saved.items():
            setattr(A, k, v)
        A.bracesmod.screen = saved_screen
        shutil.rmtree(tmp, ignore_errors=True)

    if real:
        _real(A, rc, fresh)
        _real_pool(A)

    head("NOTHING IN THE REAL BANK CHANGED")
    after = _bank_status()
    ck("git status of GUI_logs/event_bank, GUI_logs/rootcanal and "
       "GUI_logs/artifacts is as it was before the run", before == after,
       "before:\n%s\nafter:\n%s" % (before, after))

    print("")
    print("  %d ok, %d fail" % (len(OK), len(BAD)))
    return 1 if BAD else 0


def _synthetic(A, rc, cfcmod, stamp_t, kinds):
    head("PARAMETERS: WHAT IS A READ AND WHAT IS A FIT")
    ck("the job stages are declared, so progress is not silently dropped",
       {rc.STAGE_READ, rc.STAGE_SETS} <= {n for n, _u in cfcmod.STAGES})
    ck("no fit setting is in the read key",
       not set(rc.Params.READ_KEYS) & set(rc.Params.FIT_KEYS))
    base = rc.Params(entry_id="x", stamps_hash="abc")
    for kw in ({"lo_hz": 3}, {"hi_hz": 200}, {"band_lo": 300},
               {"band_hi": 1800}, {"win_ms": 10}, {"flips": [3]},
               {"cross_ms": 120},
               {"centres": [[0, 0, 0], [1, 1, 1]]}):
        ck("changing %s leaves the read where it is" % list(kw)[0],
           rc.Params(entry_id="x", stamps_hash="abc", **kw).read_hash()
           == base.read_hash())
    ck("a different list of stamps is a different read",
       rc.Params(entry_id="x", stamps_hash="abd").read_hash()
       != base.read_hash())
    ck("the live set and the version it was banked as are one read",
       rc.Params(entry_id="x", stamps_hash="abc",
                 from_version="3").read_hash() == base.read_hash())
    for kw, what in (({"filt": "custom", "hi_hz": 900},
                      "a lowpass above 400 Hz"),
                     ({"band_hi": 2600}, "a band past the 2500 Hz Nyquist"),
                     ({"band_hi": 2100},
                      "a band past the 2000 Hz anti-alias corner, where the "
                      "read is off the raw file by up to 9.5 dB"),
                     # Corners only mean anything on a custom filter: a
                     # preset is its own numbers and ignores them.
                     ({"filt": "custom", "lo_hz": 50, "hi_hz": 20},
                      "a filter upside down"),
                     ({"centres": [[0, 0], [1, 1]]}, "centres of two numbers"),
                     ({"win_ms": 0}, "a zero amplitude window"),
                     ({"cross_ms": 5}, "a half-width search under 10 ms"),
                     ({"cross_ms": 250}, "a half-width search over 200 ms")):
        try:
            rc.Params(**kw)
            ck("%s is refused with a sentence" % what, False, "accepted")
        except rc.RootCanalError as exc:
            ck("%s is refused with a sentence" % what,
               len(str(exc)) > 30 and str(exc).endswith("."), str(exc))

    head("v1's MEASUREMENT, ON A TRACE WHOSE ANSWER IS KNOWN")
    fs = 2000.0
    tt = (np.arange(1001) - 500) / fs
    # Narrow enough that the 30-60 ms flanks are quiet. A wider one lifts
    # its own baseline, which is v1's method and not something to test away.
    for fwhm in (8.0, 14.0, 20.0):
        sd = fwhm / 1000.0 / 2.3548
        y = 120.0 - 600.0 * np.exp(-0.5 * (tt / sd) ** 2)
        m = rc.measure_peak(y, 500, fs, "min", 25.0, 50.0)
        ck("a %g ms FWHM Gaussian measures %g ms (got %.3f) and 600 uV from "
           "its own 120 uV baseline (got %.1f)" % (fwhm, fwhm, m["hw_ms"],
                                                    m["amp_uV"]),
           abs(m["hw_ms"] - fwhm) < 0.05 and abs(m["amp_uV"] - 600) < 1.0
           and abs(m["baseline_uV"] - 120) < 0.5)
    m = rc.measure_peak(-600 * plateau(tt), 500, fs, "min", 25.0, 50.0)
    ck("a crossing the +-50 ms search never finds is unresolved, and NaN "
       "rather than the window edge",
       m["unresolved"] and not np.isfinite(m["hw_ms"]), m)
    m = rc.measure_peak(-600 * plateau(tt), 500, fs, "min", 25.0, WIDER_MS)
    ck("the same event resolves with the search at %g ms (hw %.2f ms, the "
       "plateau's 58)" % (WIDER_MS, m["hw_ms"]),
       not m["unresolved"] and abs(m["hw_ms"] - 58.0) < 0.5)
    ck("a fresh question searches v1's 50 ms", rc.Params().cross_ms == 50.0
       and rc.V1_CROSS_MS == 50.0)

    head("SYNTHETIC READ, THROUGH THE REAL DECIMATION AND SPECTRA")
    chans = fake_channels()
    stamps = [{"t": t} for t in stamp_t]
    p = rc.Params(entry_id="fake", stamps_hash=rc.stamps_hash(stamps))
    got = rc.read(fake_session(), chans, stamps, p,
                  bad={BAD_CH: "marked bad on this recording"})
    ck("every event read, none missed", not got["missed"]
       and got["snip"].shape == (len(stamps), len(NUMS), 1001),
       (got["missed"], got["snip"].shape))
    ck("stored at 2 kHz and 5 kHz", got["snip_fs"] == 2000.0
       and got["read_fs"] == 5000.0, (got["snip_fs"], got["read_fs"]))
    res = rc.fit(got, p)
    ev = res["events"]
    ds = [e for e, k in zip(ev, kinds) if k == "ds"]
    ied = [e for e, k in zip(ev, kinds) if k == "ied"]
    pla = [e for e, k in zip(ev, kinds) if k == "plateau"][0]
    lng = [e for e, k in zip(ev, kinds) if k == "long"][0]
    ck("the max-amp contact is the one the events were put on, every time",
       all(e["contact"] == MAX_CH for e in ev),
       [e["contact"] for e in ev])
    ck("the bad contact never wins, for amplitude or for power",
       all(e["contact"] != BAD_CH and e["hf_contact"] != BAD_CH for e in ev))
    amps = np.array([e["amp_uV"] for e in ds])
    hws = np.array([e["hw_ms"] for e in ds])
    ck("DS amplitude is %g uV to 3%% after a 1-100 Hz filter (got %.0f-%.0f)"
       % (DS_AMP, amps.min(), amps.max()),
       np.all(np.abs(amps - DS_AMP) < 0.03 * DS_AMP))
    ck("DS half-width is %g ms to 0.5 ms (got %.2f-%.2f)"
       % (DS_FWHM, hws.min(), hws.max()),
       np.all(np.abs(hws - DS_FWHM) < 0.5))
    ck("the polarity is the one the events have",
       all(e["polarity"] == "min" for e in ds + ied))
    # One 40-50 ms window is a single Welch segment, so each event's dB
    # scatters by about 2 dB whatever the implementation -- the medians are
    # what can be held to a worked-out number, and the spread to a bound.
    want = _expected_burst_db()
    hf_i = np.array([e["hf_db"] for e in ied])
    ck("a 700 Hz, %g uV burst in %g uV noise measures %+.1f dB, as worked "
       "out by hand (median %+.2f, range %+.1f to %+.1f)"
       % (BURST_UV, NOISE_UV, want, np.median(hf_i), hf_i.min(), hf_i.max()),
       abs(np.median(hf_i) - want) < 1.0 and np.all(np.abs(hf_i - want) < 5))
    D, _best, _row = rc.hf_db(got, p)
    quiet = [NUMS.index(n) for n in NUMS if n not in (MAX_CH, BAD_CH)]
    noise_db = D[:, quiet].ravel()
    ck("contacts with no burst measure about 0 dB (median %+.2f, mean "
       "%+.2f, range %+.1f to %+.1f, over %d)"
       % (np.median(noise_db), np.mean(noise_db), noise_db.min(),
          noise_db.max(), noise_db.size),
       abs(np.median(noise_db)) < 0.75 and abs(np.mean(noise_db)) < 0.75
       and np.all(np.abs(noise_db) < 7))
    ck("the bad contact's dB is withheld, not measured",
       np.all(np.isnan(D[:, NUMS.index(BAD_CH)])))

    head("HALF-WIDTH UNRESOLVED: ASSIGNED ON THE AXES IT HAS")
    for e, name in ((pla, "the +56 ms plateau"), (lng, "the +95 ms one")):
        ck("%s is unresolved at 50 ms and assigned on 2 of 3 axes" % name,
           e["unresolved"] and e["hw_ms"] is None and e["partial"]
           and e["axes"] == 2 and e["missing"] == ["hw_ms"]
           and not e["wide"] and e["cls"] in ("ds", "ied")
           and e["z"][1] is None and e["z"][0] is not None
           and e["z"][2] is not None, e)
    ck("nothing is made up for the missing axis (its z is null)",
       pla["z"][1] is None and lng["z"][1] is None)
    ck("k-means was fitted on the complete events only",
       res["n_used"] == len(ev) - 2 and res["n_placed"] == len(ev),
       (res["n_used"], res["n_placed"]))
    Cz = np.array([c["z"] for c in res["centres"]])
    for e in (pla, lng):
        d = ((Cz[:, [0, 2]] - np.array([e["z"][0], e["z"][2]])) ** 2).sum(1)
        ck("event %d went to the nearer centre on amplitude and HF alone"
           % e["i"], int(np.argmin(d)) == e["cluster"])
    ck("counted as partial, and not as unmeasured",
       res["counts"]["partial"] == 2 and res["counts"]["unmeasured"] == 0
       and res["counts"]["wide"] == 0, res["counts"])
    ck("the rule says so",
       "2 assigned on 2 of 3 axes (half-width unresolved even at 50 ms)"
       in res["rule"], res["rule"])
    full = [e for e in ev if e["axes"] == 3]
    ck("complete events carry axes 3 and no flags",
       all(not e["partial"] and not e["missing"] and not e["wide"]
           for e in full) and len(full) == len(ev) - 2)

    head("THE WIDER SEARCH")
    pw = rc.Params(entry_id="fake", stamps_hash=p.stamps_hash,
                   cross_ms=WIDER_MS)
    ck("the search setting is not part of the read",
       pw.read_hash() == p.read_hash())
    rw = rc.fit(got, pw)
    ew = rw["events"]
    ck("at %g ms the +56 ms plateau resolves, and is flagged wide (hw %s)"
       % (WIDER_MS, ew[pla["i"]]["hw_ms"]),
       ew[pla["i"]]["hw_ms"] is not None
       and abs(ew[pla["i"]]["hw_ms"] - 58.0) < 1.5
       and ew[pla["i"]]["wide"] and ew[pla["i"]]["axes"] == 3
       and not ew[pla["i"]]["partial"], ew[pla["i"]])
    ck("the +95 ms one is still unresolved, still partial",
       ew[lng["i"]]["partial"] and ew[lng["i"]]["hw_ms"] is None
       and not ew[lng["i"]]["wide"])
    ck("nothing else is wide: a crossing inside 50 ms is v1's answer",
       [e["i"] for e in ew if e["wide"]] == [pla["i"]])
    same = all((a["hw_ms"] is None and b["hw_ms"] is None)
               or (a["hw_ms"] is not None and b["hw_ms"] is not None
                   and abs(a["hw_ms"] - b["hw_ms"]) < 1e-9)
               for a, b in zip(ev, ew) if not b["wide"])
    ck("and every half-width v1 could already find is unchanged", same)
    ck("counts: 1 wide, 1 partial",
       rw["counts"]["wide"] == 1 and rw["counts"]["partial"] == 1,
       rw["counts"])
    ck("the rule says the search was widened",
       "1 resolved only with the half-width search widened to 80 ms"
       in rw["rule"] and "1 assigned on 2 of 3 axes" in rw["rule"],
       rw["rule"])
    try:
        rc.fit(dict(got, snip_ms=150.0),
               rc.Params(entry_id="fake", stamps_hash=p.stamps_hash,
                         cross_ms=120))
        ck("a search the stored snippet cannot carry is refused", False,
           "accepted")
    except rc.RootCanalError as exc:
        ck("a search the stored snippet cannot carry is refused",
           "100 ms at most" in str(exc), str(exc))

    head("ONE AXIS LEFT: UNCLASSIFIED")
    flat = dict(got)
    flat["snip"] = np.array(got["snip"], copy=True)
    i_flat = [e["i"] for e in ds][1]
    flat["snip"][i_flat] = 0
    flat.pop("_memo", None)
    rfl = rc.fit(flat, p)
    ef = rfl["events"][i_flat]
    ck("a flat event has no amplitude and no half-width, but still an HF "
       "number", ef["amp_uV"] is None and ef["hw_ms"] is None
       and ef["hf_db"] is not None, ef)
    ck("so it is missing two axes and stays null",
       ef["axes"] is None and ef["cls"] is None and ef["cluster"] is None
       and ef["z"] is None and ef["missing"] == ["amp_uV", "hw_ms"]
       and not ef["partial"], ef)
    ck("counted as unmeasured, which now means fewer than two axes",
       rfl["counts"]["unmeasured"] == 1 and rfl["counts"]["partial"] == 2,
       rfl["counts"])

    head("K-MEANS AND THE NAMING RULE")
    ck("every burst event is called IED and every plain one DS",
       all(e["cls"] == "ied" for e in ied) and all(e["cls"] == "ds"
                                                  for e in ds),
       [(k, e["cls"]) for e, k in zip(ev, kinds)])
    ied_c = [c for c in res["centres"] if c["cls"] == "ied"][0]
    ds_c = [c for c in res["centres"] if c["cls"] == "ds"][0]
    ck("the IED centre is the one with more HF power, in raw dB",
       ied_c["raw"][2] > ds_c["raw"][2])
    ck("the rule sentence names the band and both centres' dB",
       "500–1000 Hz" in res["rule"] and ("%+.1f" % ied_c["raw"][2])
       in res["rule"] and ("%+.1f" % ds_c["raw"][2]) in res["rule"],
       res["rule"])
    ck("k-means' own clusters come back DS first",
       res["centres"][0]["cls"] == "ds" and not res["manual_centres"])
    ck("the HF axis label carries the band",
       res["axes"][2]["label"] == "500–1000 Hz power"
       and res["axes"][2]["unit"] == "dB re baseline")
    zs = np.array([e["z"] for e in ev if e["axes"] == 3])
    ck("each axis is z-scored over the complete events",
       np.allclose(zs.mean(axis=0), 0, atol=1e-9)
       and np.allclose(zs.std(axis=0), 1, atol=1e-9))
    again = rc.fit(got, p)
    ck("the same question gives the same answer twice (fixed seed)",
       [e["cls"] for e in again["events"]] == [e["cls"] for e in ev])
    r_band = rc.fit(got, rc.Params(entry_id="fake",
                                   stamps_hash=p.stamps_hash,
                                   band_lo=1500, band_hi=2000))
    ck("moving the band away from the burst changes the HF axis, and says "
       "so on the label",
       r_band["axes"][2]["label"] == "1500–2000 Hz power"
       and max(e["hf_db"] for e, k in zip(r_band["events"], kinds)
               if k == "ied") < want - 10)

    head("THE OVERRIDES, AND REBUILDING FROM PARAMETERS ALONE")
    i_ds = [e["i"] for e in ds][0]
    pf = rc.Params(entry_id="fake", stamps_hash=p.stamps_hash,
                   flips=[i_ds, i_flat])
    rf = rc.fit(flat, pf)
    rfl0 = rfl
    ck("a flipped DS event comes back IED, marked as flipped",
       rf["events"][i_ds]["cls"] == "ied" and rf["events"][i_ds]["flipped"])
    ck("and it moves one event between the counts",
       rf["counts"]["ied"] == rfl0["counts"]["ied"] + 1
       and rf["counts"]["ds"] == rfl0["counts"]["ds"] - 1)
    ck("a flip on an unmeasured event is reported, not applied",
       rf["flips_ignored"] == [i_flat]
       and rf["events"][i_flat]["cls"] is None)
    pp = rc.Params(entry_id="fake", stamps_hash=p.stamps_hash,
                   flips=[lng["i"]])
    rp = rc.fit(got, pp)
    ck("a partial event can be flipped like any other",
       rp["events"][lng["i"]]["flipped"]
       and rp["events"][lng["i"]]["cls"] != lng["cls"]
       and rp["events"][lng["i"]]["partial"])
    rebuilt = rc.fit(flat, rc.Params(**rf["params"]))
    ck("a fit rebuilt from nothing but the params it returned is the same "
       "fit", [(e["cls"], e["flipped"], e["z"]) for e in rebuilt["events"]]
       == [(e["cls"], e["flipped"], e["z"]) for e in rf["events"]])
    # Drag the DS centre most of the way onto the IED one.
    C = [c["z"] for c in res["centres"]]
    dragged = [list(np.array(C[0]) * 0.1 + np.array(C[1]) * 0.9), C[1]]
    pc = rc.Params(entry_id="fake", stamps_hash=p.stamps_hash,
                   centres=dragged)
    rc_ = rc.fit(got, pc)
    Zc = np.array(dragged)
    ok_near = True
    for e in rc_["events"]:
        if e["z"] is None:
            continue
        k = [j for j in range(3) if e["z"][j] is not None]
        zz = np.array([e["z"][j] for j in k])
        near = int(np.argmin(((Zc[:, k] - zz) ** 2).sum(axis=1)))
        ok_near &= (near == e["cluster"])
    ck("a dragged centre re-assigns every event to its nearest centre, the "
       "partial ones on the axes they have", ok_near and rc_["manual_centres"])
    ck("and the flags survive the drag",
       rc_["events"][pla["i"]]["partial"] and rc_["events"][lng["i"]]["partial"]
       and rc_["events"][pla["i"]]["axes"] == 2
       and rc_["counts"]["partial"] == 2
       and "2 assigned on 2 of 3 axes" in rc_["rule"], rc_["counts"])
    pcw = rc.Params(entry_id="fake", stamps_hash=p.stamps_hash,
                    centres=dragged, cross_ms=WIDER_MS)
    rcw = rc.fit(got, pcw)
    ck("and a dragged fit at the wider search keeps its wide flag",
       rcw["events"][pla["i"]]["wide"] and rcw["counts"]["wide"] == 1
       and rcw["counts"]["partial"] == 1)
    ck("the dragged centre sticks where it was put",
       np.allclose(rc_["centres"][0]["z"], dragged[0]))
    ck("the rule says the centres were placed by hand",
       "by hand" in rc_["rule"], rc_["rule"])
    rebuilt = rc.fit(got, rc.Params(**rc_["params"]))
    ck("and that, too, rebuilds from its params",
       [e["cls"] for e in rebuilt["events"]]
       == [e["cls"] for e in rc_["events"]])

    head("AVERAGES: ONE EVENT IS ITSELF, AND FILTERING ONCE IS EXACT")
    i0, i1 = ied[0]["i"], ied[1]["i"]
    g1 = rc.group_view([rc.group_parts(got, p, [i0])], p, label="one")
    e1 = rc.event_view(got, p, i0)
    base1 = e1["trace"]["baseline"]
    ck("the average of one event is that event's own trace, less its "
       "baseline",
       g1["trace"]["contact"] == e1["trace"]["contact"]
       and np.allclose(np.array(g1["trace"]["y"], float),
                       np.array(e1["trace"]["y"], float) - base1, atol=1e-6),
       (g1["trace"]["contact"], e1["trace"]["contact"]))
    ck("and its spread is zero", np.allclose(g1["trace"]["sd"], 0, atol=1e-6))
    ck("its stack is that event's stack",
       np.allclose(np.array(g1["stack"]["rows"], float),
                   np.array(e1["stack"]["rows"], float), atol=1e-6))
    ck("and its CSD that event's CSD",
       np.allclose(np.array(g1["csd"]["rows"], float),
                   np.array(e1["csd"]["rows"], float), atol=1e-6))
    # Linearity, which is why the stack and the CSD are filtered once: the
    # average of two filtered snippets against the filtered average.
    fs_ = float(got["snip_fs"])
    two = [rc._filter(got["snip"][i], p, fs_) for i in (i0, i1)]
    once = rc._filter((np.asarray(got["snip"][i0], float)
                       + np.asarray(got["snip"][i1], float)) / 2.0, p, fs_)
    ck("filtering the average is filtering each and averaging, to float "
       "precision", np.allclose((two[0] + two[1]) / 2.0, once, atol=1e-6))
    pds = rc.Params(entry_id="fake", stamps_hash=p.stamps_hash, filt="ds")
    twod = [rc._filter(got["snip"][i], pds, fs_) for i in (i0, i1)]
    onced = rc._filter((np.asarray(got["snip"][i0], float)
                        + np.asarray(got["snip"][i1], float)) / 2.0, pds, fs_)
    ck("and with the mains fitted out too (a projection, so still linear)",
       np.allclose((twod[0] + twod[1]) / 2.0, onced, atol=1e-6))
    gi = rc.group_view([rc.group_parts(got, p, [e["i"] for e in ied])], p,
                       label="IED")
    ck("a cluster's average counts every event in it, and carries its spread",
       gi["n"] == len(ied) and len(gi["trace"]["sd"]) == len(gi["trace"]["y"])
       and gi["trace"]["n"] == len(ied))
    try:
        rc.group_parts(got, p, [])
        ck("an empty set is refused", False)
    except rc.RootCanalError:
        ck("an empty set is refused", True)

    head("CLUSTERS DRAWN BY HAND")
    held = [e["i"] for e in ied[:3]]
    dr = rc.fit(got, rc.Params(entry_id="fake", stamps_hash=p.stamps_hash,
                               drawn=[{"events": held, "call": "ds"}]))
    ck("a drawn cluster comes after k-means' own, with its call, marked drawn",
       len(dr["clusters"]) == 3 and dr["clusters"][2]["call"] == "ds"
       and dr["clusters"][2]["call_by"] == "drawn"
       and dr["clusters"][2]["n"] == 3, [c["call_by"] for c in dr["clusters"]])
    ck("its events are in it, called as drawn",
       all(dr["events"][i]["cluster"] == 2 and dr["events"][i]["cls"] == "ds"
           for i in held))
    X = np.array([[e["amp_uV"] or np.nan, e["hw_ms"] or np.nan,
                   e["hf_db"] or np.nan] for e in ev], float)
    rest = rc.cluster_core(np.delete(X, held, axis=0), k=2)
    ck("they are held out of k-means: its centres are where they would be "
       "without them",
       np.allclose(np.array([c["centre_raw"] for c in dr["clusters"][:2]]),
                   rest["raw_c"], atol=1e-6))
    ck("the rule says so", "drawn by hand" in dr["rule"], dr["rule"])
    ck("and a fit with a drawn cluster rebuilds from its params",
       [e["cls"] for e in rc.fit(got, rc.Params(**dr["params"]))["events"]]
       == [e["cls"] for e in dr["events"]])
    try:
        rc.Params(drawn=[{"events": [1, 2], "call": "ds"},
                         {"events": [2, 3], "call": "ied"}])
        ck("an event in two drawn clusters is refused", False)
    except rc.RootCanalError:
        ck("an event in two drawn clusters is refused", True)

    head("THE CLICK PANEL, AND A READ FILED AND READ BACK")
    v = rc.event_view(got, p, ied[0]["i"])
    tr = v["trace"]
    ck("the trace is the max-amp contact, with its numbers matching the fit",
       tr["contact"] == MAX_CH
       and abs(tr["amp_uV"] - ied[0]["amp_uV"]) < 1e-6
       and abs(tr["hw_ms"] - ied[0]["hw_ms"]) < 1e-6)
    ck("half-width span and half level are drawable",
       tr["left_ms"] < tr["peak_ms"] < tr["right_ms"]
       and abs((tr["right_ms"] - tr["left_ms"]) - tr["hw_ms"]) < 1e-6
       and tr["half_uV"] is not None and tr["baseline"] is not None)
    ck("no array in time is longer than 400 points",
       len(tr["t_ms"]) <= 400 and len(v["stack"]["t_ms"]) <= 400
       and all(len(r) <= 400 for r in v["csd"]["rows"]))
    sp = v["spectrum"]
    ck("the spectrum has event and baseline on one grid, and the band",
       len(sp["f"]) == len(sp["event"]) == len(sp["baseline"])
       and sp["band"] == [500.0, 1000.0])
    ck("the stack marks the bad contact",
       v["stack"]["bad"][NUMS.index(BAD_CH)] and sum(v["stack"]["bad"]) == 1)
    ck("the CSD has a symmetric colour limit",
       v["csd"]["clim"][1] > 0
       and v["csd"]["clim"][0] == -v["csd"]["clim"][1])
    # THE CSD IS ON THE DENTATE-SPIKE FILTER, not the fit filter: 60 Hz
    # notch then 5-100 Hz, X-ray's. On the fit filter, mains that differs a
    # little between contacts survived the second difference -- 72-78% of
    # CSD power at 55-65 Hz on PTEN m1 s2 and m1 s8, while the traces
    # beside it carried 1-5%.
    ck("the CSD says it is on the dentate-spike filter",
       v["csd"].get("band") == [5.0, 100.0]
       and v["csd"].get("notch_hz") == 60.0
       and "mains taken out" in (v["csd"].get("filter") or ""),
       v["csd"].get("filter"))
    fs_ = 2000.0
    tt = np.arange(1000) / fs_
    x = np.vstack([np.sin(2 * np.pi * 60.0 * tt) * 100.0
                   + np.sin(2 * np.pi * 20.0 * tt) * 10.0])
    y = rc._ds_filter(x, fs_)[0][250:750]
    F = np.fft.rfftfreq(500, 1 / fs_)
    Pw = np.abs(np.fft.rfft(y * np.hanning(500))) ** 2
    at60 = Pw[(F > 55) & (F < 65)].sum()
    at20 = Pw[(F > 15) & (F < 25)].sum()
    ck("the filter takes 60 Hz down by more than 20 dB and leaves 20 Hz",
       at60 < at20 * 0.1, "60 Hz %.3g vs 20 Hz %.3g" % (at60, at20))
    # And it leaves a dentate spike alone: a 1 mV Gaussian, 8 ms SD, in the
    # middle of the snippet, through the mains removal alone.
    gs = 1000.0 * np.exp(-0.5 * ((tt - 0.25) / 0.008) ** 2)
    moved = np.abs(rc._line_out(gs[None, :], fs_)[0] - gs).max()
    ck("fitting the mains out moves a 1 mV spike by under 1%",
       moved < 10.0, "%.2f uV" % moved)
    tmpf = os.path.join(tempfile.mkdtemp(prefix="rc_npz_"), "r.npz")
    rc.save_read(tmpf, got)
    back = rc.load_read(tmpf)
    ck("a read filed and loaded back fits to the same answer",
       [e["cls"] for e in rc.fit(back, p)["events"]]
       == [e["cls"] for e in ev])
    shutil.rmtree(os.path.dirname(tmpf), ignore_errors=True)


def _routes(A, rc, cfcmod, eventbank, storemod, toolresults, tmp, stamp_t,
            kinds, fake):
    head("THE PICTURE GATE")
    ck("a PNG data URI is accepted", A._png_bytes(PNG_URI) == PNG1)
    ck("a JPEG-labelled one is refused",
       A._png_bytes(PNG_URI.replace("image/png", "image/jpeg")) is None)
    ck("base64 of something else is refused",
       A._png_bytes("data:image/png;base64,"
                    + base64.b64encode(b"not a png").decode()) is None)

    # A throwaway bank, store and vault, in a temp folder. Everything the
    # routes write goes here.
    logs = os.path.join(tmp, "GUI_logs")
    os.makedirs(logs)
    st = storemod.Store(logs, auto_stage=False)
    bank = eventbank.EventBank(logs, st)
    vault = toolresults.ToolResults(
        logs, "rootcanal", st,
        keys=tuple(rc.Params.READ_KEYS) + tuple(rc.Params.FIT_KEYS))
    outdir = os.path.join(tmp, "Results")
    os.makedirs(outdir)
    written = []

    def fake_save(blob, filename, subdir=None, lane="exhibit"):
        path = os.path.join(outdir, filename)
        with open(path, "wb") as fh:
            fh.write(blob)
        written.append(path)
        return {"rel": filename, "path": path}

    A.BANK, A.STORE, A.ROOTCANAL, A.save_output = bank, st, vault, fake_save
    A._braces_session = lambda rec: (fake_session(), {})
    A._braces_channels = lambda sess: fake_channels()
    A._stored_for = lambda sess: {}
    A.bracesmod.screen = lambda *a, **k: {}

    head("THE VERSION TAG")
    who = "check_rootcanal"
    events = [{"start": t, "label": "Dentate Spike", "label_id": "spike",
               "from_t": t - 0.002, "channel": MAX_CH, "amplitude": 1.0}
              for t in stamp_t]
    # Two rejections, which Root Canal never reads and must carry as-is.
    events += [{"start": 41.0, "label": "Garbage", "label_id": "garbage"},
               {"start": 42.5, "label": "Garbage", "label_id": "garbage"}]
    first = bank.add({
        "id": "rcchk000001", "gid": "s_rootcanal_check", "type": "ds",
        "name": "check set", "session_label": "CHECK m0 s0",
        "project": "CHECK", "mouse": 0, "session": 0,
        "events": events, "curated": True, "curation_label": "*",
        "pipeline": "check_rootcanal", "added_by": who,
        "aligned": {"tool": "check"}, "version_tag": "curated-check",
        "label_names": {"spike": "Dentate Spike", "garbage": "Garbage"}})
    ck("a version minted with a tag carries it",
       first["versions"][-1].get("tag") == "curated-check")
    ck("and named_versions() passes it through",
       A.named_versions(first["versions"])[-1].get("tag") == "curated-check")
    again = bank.add(dict(first, events=first["events"], added_by=who,
                          pipeline="check_rootcanal", curated=True,
                          version_tag="should-not-appear"))
    ck("a re-bank that changes nothing mints no version, so tags nothing",
       not again.get("new_version")
       and all(v.get("tag") != "should-not-appear"
               for v in again["versions"]))
    n_versions0 = len(bank.get("rcchk000001")["versions"])

    head("READ, FIT AND EVENT THROUGH THE ROUTES")
    c = A.app.test_client()
    r = c.post("/api/rootcanal/fit", json={"entry_id": "rcchk000001"})
    ck("a fit before any read is refused with a sentence, 400",
       r.status_code == 400 and not r.get_json()["ok"]
       and "Read it first" in r.get_json()["error"], r.get_json())
    r = c.post("/api/rootcanal/read", json={"entry_id": "rcchk000001"})
    js = r.get_json()
    ck("a read starts a job", r.status_code == 200 and js["ok"]
       and js["cached"] is False and js["job"] and js["n"] == len(stamp_t),
       js)
    job = cfcmod.get(js["job"]["id"])
    for _ in range(600):
        if job.status != "running":
            break
        time.sleep(0.05)
    ck("the job finishes", job.status == "done", (job.status, job.error))
    snap = job.snapshot()
    ck("its progress is counted on Root Canal's own stage",
       any(s["name"] == rc.STAGE_READ for s in snap["stages"]),
       snap["stages"])
    r = c.post("/api/rootcanal/read", json={"entry_id": "rcchk000001"})
    js2 = r.get_json()
    ck("asked again, it is cached, with no job",
       js2["cached"] is True and js2["job"] is None
       and js2["read"] == js["read"], js2)
    r = c.post("/api/rootcanal/fit", json={"entry_id": "rcchk000001"})
    fit = r.get_json()
    ck("the fit answers in the contract's shape",
       r.status_code == 200 and fit["ok"]
       and {"n", "n_used", "axes", "events", "centres", "rule", "counts",
            "params"} <= set(fit)
       and {"i", "t", "amp_uV", "hw_ms", "hf_db", "z", "cluster", "cls",
            "flipped", "contact", "contact_row", "polarity"}
       <= set(fit["events"][0])
       and {"z", "raw", "cls", "n"} <= set(fit["centres"][0]),
       fit if not fit.get("ok") else sorted(fit))
    n_ied = sum(1 for k in kinds if k == "ied")
    ck("and it finds the %d IEDs" % n_ied, fit["counts"]["ied"] == n_ied,
       fit["counts"])
    r = c.post("/api/rootcanal/fit", json={"entry_id": "rcchk000001",
                                          "filt": "custom", "hi_hz": 5000})
    ck("a bad setting comes back as a 400 with a sentence",
       r.status_code == 400 and "400 Hz" in r.get_json()["error"])
    r = c.post("/api/rootcanal/event", json={"entry_id": "rcchk000001",
                                            "i": 1})
    ev = r.get_json()
    ck("the event view answers in the contract's shape",
       r.status_code == 200 and ev["ok"]
       and {"trace", "spectrum", "stack", "csd"} <= set(ev)
       and {"t_ms", "y", "baseline", "peak_ms", "peak_uV", "left_ms",
            "right_ms", "half_uV", "contact", "polarity"} <= set(ev["trace"])
       and {"f", "event", "baseline", "band"} <= set(ev["spectrum"])
       and {"t_ms", "rows", "nums", "bad", "gain"} <= set(ev["stack"])
       and {"t_ms", "rows", "clim"} <= set(ev["csd"]), sorted(ev))

    head("COMMIT: DS vN+1 AND AN IED ENTRY")
    body = {"entry_id": "rcchk000001", "by": who, "note": "check",
            "pngs": {"space": PNG_URI, "flat": "data:image/png;base64,AAAA"}}
    r = c.post("/api/rootcanal/commit", json=body)
    cm = r.get_json()
    ck("the commit answers in the contract's shape",
       r.status_code == 200 and cm["ok"]
       and {"ds_entry", "ds_version", "ied_entry", "ied_version", "removed",
            "kept"} <= set(cm), cm)
    ds = bank.get("rcchk000001")
    tip = ds["versions"][-1]
    ck("the DS set got exactly one new version, tagged rootcanal",
       len(ds["versions"]) == n_versions0 + 1 and tip.get("tag") ==
       "rootcanal", [(v.get("v"), v.get("tag")) for v in ds["versions"]])
    ck("holding everything but the %d IEDs (removed %d, kept %d)"
       % (n_ied, cm["removed"], cm["kept"]),
       cm["removed"] == n_ied and ds["n"] == len(events) - n_ied
       and cm["kept"] == len(stamp_t) - n_ied)
    ied_times = {round(stamp_t[i], 4) for i, k in enumerate(kinds)
                 if k == "ied"}
    left = {round(e["start"], 4) for e in ds["events"]}
    ck("the IEDs are the ones that left", not (ied_times & left))
    ck("the rejections Root Canal never read are carried as they were",
       sum(1 for e in ds["events"] if e.get("label_id") == "garbage") == 2)
    kept = [e for e in ds["events"] if e.get("label_id") == "spike"]
    ck("every kept event keeps its fields (from_t, channel, amplitude)",
       all(e.get("from_t") is not None and e.get("channel") == MAX_CH
           and e.get("amplitude") == 1.0 for e in kept))
    ck("still curated, still aligned",
       ds.get("specified") and ds.get("aligned"))
    ck("the version note says how many and why",
       ("%d hidden IED" % n_ied) in tip.get("note", "")
       and "called IED" in tip.get("note", ""), tip.get("note"))
    part_t = [stamp_t[i] for i, k in enumerate(kinds)
              if k in ("plateau", "long")]
    ck("the note names the partial events, and the search they were "
       "unresolved at",
       "2 assigned on 2 of 3 axes (half-width unresolved even at 50 ms)"
       in tip.get("note", "")
       and ("t = %s s" % ", ".join("%.3f" % t for t in part_t))
       in tip.get("note", "")
       and "half-width search ±50 ms" in tip.get("note", ""),
       tip.get("note"))
    ied = bank.get(cm["ied_entry"])
    ck("the IEDs are an IED entry of their own, uncurated",
       ied and ied.get("type") == "ied" and not ied.get("specified")
       and ied.get("name") == "Hidden IEDs (Root Canal)"
       and ied["n"] == n_ied)
    par = (ied.get("source") or {}).get("parameters") or {}
    ck("linked back to the DS entry, its version and the fit",
       par.get("from_entry") == "rcchk000001" and "from_version" in par
       and par.get("band_lo") == 500.0 and "flipped" in par, par)
    ck("the IED entry's parameters carry partial_t, wide_t and cross_ms",
       par.get("partial_t") == part_t and par.get("wide_t") == []
       and par.get("cross_ms") == 50.0, par)
    ck("arriving as candidates, with no label on any of them",
       all(not e.get("label") for e in ied["events"]))
    ck("the one real PNG was filed and the fake one was not",
       len(written) == 1 and written[0].endswith("_space_%s.png"
                                                 % cm["params_hash"][:8]),
       written)
    res = vault.get("s_rootcanal_check", cm["params_hash"])
    ck("the numbers are in the results bank, keyed on the question",
       res and res.get("kind") == "classification"
       and len(res.get("rows") or []) == len(stamp_t)
       and res.get("ds_version") == cm["ds_version"])
    ck("so does the results record, and per event",
       res.get("partial_t") == part_t and res.get("wide_t") == []
       and res.get("cross_ms") == 50.0
       and "partial" in res.get("columns", [])
       and sum(1 for r_ in res["rows"]
               if r_[res["columns"].index("partial")]) == 2)
    ck("and the commit reports the counts",
       cm.get("partial") == 2 and cm.get("wide") == 0, cm)
    ck("and the version names where to find them",
       ("rootcanal/s_rootcanal_check__%s" % cm["params_hash"])
       in tip.get("note", ""))

    head("THE CLEANED SET, AND NOT CLEANING IT TWICE")
    n_ds_v = len(bank.get("rcchk000001")["versions"])
    n_ied_v = len(bank.get(cm["ied_entry"])["versions"])
    n_ied_entries = sum(1 for e in bank.all() if e.get("type") == "ied")
    r = c.post("/api/rootcanal/fit", json={"entry_id": "rcchk000001"})
    fj = r.get_json()
    ck("the cleaned live set fits at once, from the rows already read",
       r.status_code == 200 and fj["ok"]
       and fj["n"] == len(stamp_t) - n_ied and fj.get("subset_of")
       and fj.get("source_tag") == "rootcanal", fj.get("error") or
       (fj.get("n"), fj.get("subset_of"), fj.get("source_tag")))
    r = c.post("/api/rootcanal/commit", json=dict(body, pngs={}))
    ck("committing from Root Canal's own output is refused, with the way "
       "out", r.status_code == 400 and "again: true" in r.get_json()["error"]
       and len(bank.get("rcchk000001")["versions"]) == n_ds_v,
       r.get_json())
    src = [v for v in bank.get("rcchk000001")["versions"]
           if v.get("tag") == "curated-check"][0]

    head("COMMITTING THE SAME ANSWER AGAIN WRITES NOTHING")
    r = c.post("/api/rootcanal/commit",
               json=dict(body, pngs={}, from_version=src["id"]))
    cm2 = r.get_json()
    ck("the re-commit says nothing was written",
       cm2["ok"] and cm2["written"] == {"ds": False, "ied": False}
       and "already" in cm2, cm2)
    ck("no new DS version, no new IED version, no second IED entry",
       len(bank.get("rcchk000001")["versions"]) == n_ds_v
       and len(bank.get(cm["ied_entry"])["versions"]) == n_ied_v
       and sum(1 for e in bank.all() if e.get("type") == "ied")
       == n_ied_entries and cm2["ied_entry"] == cm["ied_entry"])

    head("A FLIP, COMMITTED FROM THE VERSION THAT WAS READ")
    flip_i = [i for i, k in enumerate(kinds) if k == "ied"][0]
    r = c.post("/api/rootcanal/commit", json=dict(
        body, pngs={}, from_version=src["id"], flips=[flip_i],
        cross_ms=WIDER_MS))
    cm3 = r.get_json()
    note3 = bank.get("rcchk000001")["versions"][-1].get("note", "")
    wide_t = [stamp_t[i] for i, k in enumerate(kinds) if k == "plateau"]
    ck("committed at the wider search, the note says which were resolved "
       "only by widening it",
       "1 resolved only with the half-width search widened to 80 ms" in note3
       and ("widened to 80 ms: t = %.3f s" % wide_t[0]) in note3, note3)
    rec3 = vault.get("s_rootcanal_check", cm3.get("params_hash"))
    ck("and the results record carries wide_t and cross_ms 80",
       rec3 and rec3.get("wide_t") == wide_t and rec3.get("cross_ms") == 80.0
       and len(rec3.get("partial_t")) == 1, rec3 and
       (rec3.get("wide_t"), rec3.get("cross_ms"), rec3.get("partial_t")))
    ied3 = bank.get(cm["ied_entry"])["versions"][-1].get("note", "")
    ck("as does the IED entry's new version",
       "widened to 80 ms" in ied3, ied3)
    ck("reading from the named version finds the same read as the live set",
       r.status_code == 200 and cm3["ok"], cm3)
    ck("the flipped IED stays in the DS set this time",
       cm3.get("removed") == n_ied - 1
       and round(stamp_t[flip_i], 4) in {
           round(e["start"], 4) for e in bank.get("rcchk000001")["events"]})
    ck("and the SAME IED entry gets a new version, not a second entry",
       cm3.get("ied_entry") == cm["ied_entry"]
       and len(bank.get(cm["ied_entry"])["versions"]) == n_ied_v + 1
       and bank.get(cm["ied_entry"])["n"] == n_ied - 1)

    head("CANDIDATES")
    r = c.get("/api/rootcanal/candidates")
    cj = r.get_json()
    row = [s for s in cj["sets"] if s["entry_id"] == "rcchk000001"]
    ck("the set is offered, with its versions named and tagged",
       row and row[0]["aligned"] is True
       and any(v.get("tag") == "rootcanal" for v in row[0]["versions"])
       and all("name" in v for v in row[0]["versions"]), row)
    ck("and it says Root Canal has been done, and where the IEDs went",
       row and row[0]["rootcanal"]["done"]
       and row[0]["rootcanal"]["ied_entry"] == cm["ied_entry"]
       and row[0]["rootcanal"]["version"], row and row[0]["rootcanal"])
    bank.add({"id": "rcchk000002", "gid": "s_rootcanal_check2",
              "type": "ds", "name": "unaligned", "events": events[:3],
              "curated": True, "pipeline": "check_rootcanal",
              "added_by": who})
    r = c.get("/api/rootcanal/candidates")
    row2 = [s for s in r.get_json()["sets"] if s["entry_id"] == "rcchk000002"]
    ck("a set Braces has not aligned is listed as not readable, and why",
       row2 and row2[0]["readable"] is False
       and row2[0]["why_not"] == "Braces hasn't aligned this set yet", row2)
    r = c.post("/api/rootcanal/read", json={"entry_id": "rcchk000002"})
    ck("and reading it is refused with a sentence",
       r.status_code == 400 and "Braces" in r.get_json()["error"])
    r = c.get("/api/rootcanal/batch/plan")
    pj = r.get_json()
    # Both blocked, for different reasons: the cleaned set because its live
    # set is Root Canal's own output (the batch plan refuses to re-clean it,
    # as the commit does), the other because Braces never aligned it.
    blk = {b["entry_id"]: b["why"] for b in pj.get("blocked") or []}
    ck("the batch plan blocks the cleaned set and the unaligned one, and "
       "says why", pj["ok"]
       and "already taken the IEDs out" in blk.get("rcchk000001", "")
       and blk.get("rcchk000002") == "Braces hasn't aligned this set yet",
       pj)

    head("STOP LANDS MID-RECORDING")
    # Every other stamp, 4 s apart, so each is its own span and there is a
    # checkpoint between every read. (2 s apart they merge into one span of
    # the whole recording, and a stop has nowhere to land but the end.)
    fake.delay = 0.004
    fake.calls = 0
    sparse = stamp_t[::2]
    stamps = [{"t": t} for t in sparse]
    p = rc.Params(entry_id="stop", stamps_hash=rc.stamps_hash(stamps))
    seen = {}

    def work(job):
        try:
            return rc.read(fake_session(), fake_channels(), stamps, p,
                           job=job)
        except cfcmod.Canceled:
            seen["canceled"] = True
            raise

    job = cfcmod.start({}, [(rc.STAGE_READ, len(NUMS))], work, 1.0)
    for _ in range(400):
        if fake.calls >= 8:
            break
        time.sleep(0.005)
    job.cancel()
    for _ in range(400):
        if job.status == "running":
            time.sleep(0.01)
    def n_reads(ts):
        return len(NUMS) * len(A.bracesmod.spans(
            ts, window_ms=rc.SNIP_MS, pad_s=rc.PAD_S,
            merge_gap=rc.MERGE_GAP_S))
    total = n_reads(sparse)
    ck("a cancelled read ends canceled, not failed", job.status == "canceled"
       and seen.get("canceled"), job.status)
    ck("and it stopped inside the recording (%d of %d reads)"
       % (fake.calls, total), fake.calls < total - 2)

    live, _n = A._dspca_stamps(bank.get("rcchk000001"), None)
    total = n_reads([e["t"] for e in live])
    fake.calls = 0
    r = c.post("/api/rootcanal/batch", json={"entries": ["rcchk000001"],
                                            "force": True})
    bj = r.get_json()
    job = cfcmod.get(bj["job"]["id"])
    for _ in range(400):
        if fake.calls >= 8:
            break
        time.sleep(0.005)
    job.cancel()
    for _ in range(400):
        if job.status == "running":
            time.sleep(0.01)
    snap = job.snapshot()
    mem = (snap.get("members") or [{}])[0]
    ck("a cancelled batch ends canceled, and its set is 'stopped', not "
       "'error'", job.status == "canceled" and mem.get("status") == "stopped",
       (job.status, mem))
    ck("and stopped inside the recording (%d of %d reads)"
       % (fake.calls, total), fake.calls < total - 2)
    fake.delay = 0.0
    r = c.post("/api/rootcanal/batch", json={"entries": ["rcchk000001"],
                                            "force": True})
    job = cfcmod.get(r.get_json()["job"]["id"])
    for _ in range(600):
        if job.status != "running":
            break
        time.sleep(0.05)
    mem = (job.snapshot().get("members") or [{}])[0]
    ck("a batch left to run marks its set done, with progress on the row",
       job.status == "done" and mem.get("status") == "done"
       and mem.get("done") == mem.get("of") == len(NUMS), mem)


def _real(A, rc, fresh):
    head("ONE REAL READ: 46fd29a77cc7, PTEN m13 s2 2023-08-01")
    rec = A.BANK.get("46fd29a77cc7")
    if not rec:
        ck("the entry is in the bank here", False, "not found")
        return
    stamps, _n = A._dspca_stamps(rec, None)
    p = rc.Params(entry_id=rec["id"], stamps_hash=rc.stamps_hash(stamps))
    rh = p.read_hash()
    gid = rec.get("gid")
    path = A.ROOTCANAL.cached_path(gid, rh, ".npz")
    took = None
    if fresh or not os.path.exists(path):
        try:
            sess, chans, stamps, p, marked = A._rootcanal_prepare(rec, None)
        except Exception as exc:                         # noqa: BLE001
            print("  skipped: the recording cannot be opened here (%s)" % exc)
            return
        from backend import braces, dspca
        bad = dict(marked)
        spec = {"band": dspca.T_DS_FREQ, "line_hz": braces.LINE_HZ,
                "line_q": braces.LINE_Q, "lfp_fs": dspca.T_LFP_FS,
                "spacing_um": p.spacing, "csd_smooth": True}
        bad.update(braces.screen(sess, chans, spec, [e["t"] for e in stamps]))
        t0 = time.time()
        got = rc.read(sess, chans, stamps, p, bad)
        took = time.time() - t0
        rc.save_read(path, got)
    got = rc.load_read(path)
    res = rc.fit(got, p)
    print("  read: %s (%s)" % (rh, ("%.0f s just now" % took) if took
                                else "from the cache"))
    print("  bad contacts: %s" % got["bad"])
    print("  n %d, n_used %d, counts %s" % (res["n"], res["n_used"],
                                           res["counts"]))
    print("  rule: %s" % res["rule"])
    for cen in res["centres"]:
        print("  %-3s centre: amp %.0f uV, hw %.1f ms, HF %+.1f dB  (n %d)"
              % (cen["cls"].upper(), cen["raw"][0], cen["raw"][1],
                 cen["raw"][2], cen["n"]))
    ck("all 296 events were read", res["n"] == 296 and not got["missed"],
       (res["n"], got["missed"]))
    ck("and nearly all were measured on all three axes",
       res["n_used"] >= 290, res["n_used"])
    ck("the dead contact (59) is out", 59 in got["bad"])



# --------------------------------------------------------------------------
# POOL
# --------------------------------------------------------------------------
def _canon_json(x):
    from backend import artifacts as artifactsmod
    return json.dumps(artifactsmod._canon(artifactsmod.plain(x)),
                      sort_keys=True)


def _blob(rng, n, amp, hw, hf, cls, sd=(60.0, 1.5, 1.5)):
    rows = []
    for _ in range(n):
        rows.append({"amp_uV": float(rng.normal(amp, sd[0])),
                     "hw_ms": float(rng.normal(hw, sd[1])),
                     "hf_db": float(rng.normal(hf, sd[2])),
                     "cls": cls, "truth": cls})
    return rows


def _member(pool, key, project, mouse, rows, gid=None):
    for k, r in enumerate(rows):
        r.setdefault("i", k)
        r.setdefault("t", 1.0 + k)
    gid = gid or "g_" + key
    return {"key": key, "entry_id": "e_" + key, "session_label": key,
            "gid": gid, "project": project,
            "mouse_key": pool.mouse_key(project, mouse, gid),
            "mouse_type": pool.mouse_type_of(project),
            "banked": True, "pin": {"params": {"cross_ms": 50.0}},
            "band": [500.0, 1000.0], "rows": rows}


def _k_and_margins_core():
    """k = 1..6, the HF ranking, relabels, and margins in the shared core."""
    from backend import rootcanal as rc
    from backend import rootcanalpool as pool
    rng = np.random.default_rng(21)
    head("k CLUSTERS, RANKED BY HF, AND RELABELS")
    ck("k = 2 is still the default", rc.Params().k == 2)
    for bad, what in ((0, "k = 0"), (7, "k = 7"), (2.5, "k = 2.5")):
        try:
            rc.Params(k=bad)
            ck("%s is refused" % what, False, "accepted")
        except rc.RootCanalError:
            ck("%s is refused" % what, True)
    try:
        rc.Params(k=3, centres=[[0, 0, 0], [1, 1, 1]])
        ck("two dragged centres for three clusters are refused", False)
    except rc.RootCanalError:
        ck("two dragged centres for three clusters are refused", True)
    try:
        rc.Params(cluster_calls={"0": "maybe"})
        ck("a relabel to neither DS nor IED is refused", False)
    except rc.RootCanalError:
        ck("a relabel to neither DS nor IED is refused", True)

    # Three blobs, separated on HF (the third column) and on amplitude.
    blobs = [(100.0, 20.0, 5.0), (300.0, 15.0, 12.0), (600.0, 10.0, 25.0)]
    X = np.vstack([rng.normal(c, (8.0, 1.0, 0.8), size=(120, 3))
                   for c in blobs])
    core = rc.cluster_core(X, k=3)
    hf = core["raw_c"][:, 2]
    ck("k = 3 finds three clusters, ranked by HF lowest first",
       core["k"] == 3 and list(hf) == sorted(hf), list(hf))
    ck("and each is one blob", sorted(int((core["lab"] == r).sum())
                                      for r in range(3)) == [120, 120, 120])
    ck("the highest-HF cluster is IED and the rest DS by the rule",
       core["calls"] == ["ds", "ds", "ied"]
       and core["call_by"] == ["rule"] * 3, core["calls"])
    one_ = rc.cluster_core(X, k=1)
    ck("k = 1 is no split: one cluster, every event DS",
       one_["k"] == 1 and one_["calls"] == ["ds"]
       and (one_["lab"] == 0).all())
    ck("and says so in words",
       "no split" in (rc.k_sentence(one_, "500–1000 Hz power") or ""))
    rl = rc.cluster_core(X, k=3, cluster_calls={"1": "ied"})
    ck("a relabel wins over the rule, and is marked as by hand",
       rl["calls"] == ["ds", "ied", "ied"]
       and rl["call_by"] == ["rule", "hand", "rule"], rl["call_by"])
    six = rc.cluster_core(X, k=6)
    ck("k = 6 runs, ranked, with one IED by the rule",
       six["k"] == 6 and six["calls"].count("ied") == 1
       and list(six["raw_c"][:, 2]) == sorted(six["raw_c"][:, 2]))
    ck("at k = 2 by the rule the original sentence is kept, word for word",
       rc.k_sentence(rc.cluster_core(X, k=2), "x") is None)

    head("MARGINS: READ ON THE SOURCE'S SCALE, FIXED OR REFINED")
    src = rc.cluster_core(X, k=2)
    margin = {"k": 2, "scale": {"mean": list(src["mu"]),
                                "sd": list(src["sd"])},
              "clusters": [{"rank": r, "call": src["calls"][r],
                            "centre_raw": list(src["raw_c"][r])}
                           for r in range(2)]}
    back = rc.cluster_core(X, margin=margin, margin_mode="fixed")
    ck("a margin applied fixed to its own source gives its own calls back",
       (back["lab"] == src["lab"]).all() and back["calls"] == src["calls"]
       and back["call_by"] == ["margin", "margin"])
    ck("and fixed means nothing moved",
       np.allclose(back["raw_c"], src["raw_c"]))
    # The boundary is raw: halfway between the two raw centres along HF,
    # an event either side lands either side, whatever the target's spread.
    mid = (src["raw_c"][0] + src["raw_c"][1]) / 2.0
    step = (src["raw_c"][1] - src["raw_c"][0]) * 0.05
    probe = np.vstack([mid - step, mid + step])
    pr = rc.cluster_core(probe, margin=margin)
    ck("on a target with a different spread, events cross where the raw "
       "boundary says", list(pr["lab"]) == [0, 1], list(pr["lab"]))
    shifted = X + np.array([0.0, 0.0, 6.0])
    rf = rc.cluster_core(shifted, margin=margin, margin_mode="refine")
    ck("refined, the centres move to fit the data and keep their calls",
       not np.allclose(rf["raw_c"], src["raw_c"])
       and rf["calls"] == src["calls"] and rf["call_by"] == ["margin"] * 2)
    ck("a margin sets k, whatever was asked",
       rc.cluster_core(X, k=5, margin=margin)["k"] == 2)
    m_lfp = {"measure": rc.measure_of(rc.Params())}
    diff = rc.margin_mismatch(m_lfp, rc.Params(filt="ds", band_lo=600,
                                               band_hi=900, cross_ms=80))
    ck("a margin from other settings names every difference",
       len(diff) == 3 and any("DS filter" in d for d in diff)
       and any("600" in d for d in diff) and any("80" in d for d in diff),
       diff)
    ck("and the same settings have none",
       rc.margin_mismatch(m_lfp, rc.Params()) == [])

    head("POOLED: k, AND COMPLETE EVENTS ONLY")
    rows = []
    for j, (a, w, h) in enumerate(X):
        rows.append({"i": j, "t": 1.0 + j, "amp_uV": float(a),
                     "hw_ms": float(w), "hf_db": float(h), "cls": "ds"})
    rows[0]["hw_ms"] = None
    mem = _member(pool, "K", "PTEN", 7, rows)
    r3 = pool.fit_pool([mem], k=3)
    ck("a pool clusters at k = 3 through the same core",
       r3["k"] == 3 and len(r3["clusters"]) == 3
       and r3["counts"]["ied"] == 120, r3["counts"])
    ck("its split axis runs DS-called to IED-called",
       r3["split_axis"]["centres_z"] is not None)
    r1 = pool.fit_pool([mem], k=1)
    ck("at k = 1 there is no split axis, and it says why",
       r1["split_axis"]["centres_z"] is None
       and r1["split_axis"]["why_none"])
    co = pool.fit_pool([mem], complete_only=True)
    ck("complete events only leaves out the one missing an axis, and counts it",
       co["n"] == len(rows) - 1 and co["counts"]["excluded"] == 1
       and co["excluded"]["by_member"] == [{"key": "K", "n": 1}]
       and co["counts"]["partial"] == 0)
    ck("and by default it is kept, placed on its two axes",
       pool.fit_pool([mem])["counts"]["partial"] == 1)


def _filter_choices():
    """None, DS, LFP or custom: what each one is, and that each is itself."""
    from backend import rootcanal as rc
    head("THE FOUR FILTERS THE AMPLITUDE AND HALF-WIDTH CAN BE MEASURED ON")
    ck("the default is still the LFP filter, so nothing fitted before moves",
       rc.Params().filt == "lfp"
       and rc.Params().fit_params() == rc.Params(filt="lfp").fit_params())
    d = rc.Params(filt="ds", lo_hz=3, hi_hz=300, order=7, mains_out=False)
    ck("a preset is its own numbers: DS is 5-100 Hz at Toothy's order, "
       "mains out, whatever else came with it",
       (d.lo_hz, d.hi_hz, d.order, d.mains_out) == (5.0, 100.0, 3, True),
       (d.lo_hz, d.hi_hz, d.order, d.mains_out))
    l = rc.Params(filt="lfp", lo_hz=3)
    ck("LFP is 1-100 Hz, order 4, mains left in",
       (l.lo_hz, l.hi_hz, l.order, l.mains_out) == (1.0, 100.0, 4, False))
    c = rc.Params(filt="custom", lo_hz=3, hi_hz=150, order=2)
    ck("custom takes its corners, and takes the mains out unless told not to",
       (c.lo_hz, c.hi_hz, c.order, c.mains_out) == (3.0, 150.0, 2, True))
    ck("and can be told not to",
       rc.Params(filt="custom", mains_out=False).mains_out is False)
    for kw, what in (({"filt": "bogus"}, "an unknown filter"),
                     ({"filt": "custom", "lo_hz": 50, "hi_hz": 20},
                      "a custom filter upside down")):
        try:
            rc.Params(**kw)
            ck("%s is refused" % what, False, "accepted")
        except rc.RootCanalError:
            ck("%s is refused" % what, True)
    ck("each says what it is in words",
       rc.Params(filt="none").filter_label().startswith("no filter")
       and "60 Hz mains out" in d.filter_label()
       and "mains left in" in l.filter_label())

    fs = 2000.0
    t = np.arange(1000) / fs
    x = np.vstack([100.0 * np.sin(2 * np.pi * 60 * t)
                   + 10.0 * np.sin(2 * np.pi * 20 * t)])
    F = np.fft.rfftfreq(500, 1 / fs)

    def power(y, lo, hi):
        Pw = np.abs(np.fft.rfft(y[250:750] * np.hanning(500))) ** 2
        return Pw[(F > lo) & (F < hi)].sum()

    raw = rc._filter(x, rc.Params(filt="none"), fs)[0]
    ck("no filter is no filter: the snippet comes back as it went in",
       np.allclose(raw, x[0]))
    dsy = rc._filter(x, d, fs)[0]
    ck("the DS filter takes 60 Hz down by more than 20 dB and keeps 20 Hz",
       power(dsy, 55, 65) < 0.1 * power(dsy, 15, 25),
       "%.3g vs %.3g" % (power(dsy, 55, 65), power(dsy, 15, 25)))
    lfy = rc._filter(x, l, fs)[0]
    ck("the LFP filter leaves the mains where it was, as the literature band "
       "does", power(lfy, 55, 65) > 10 * power(lfy, 15, 25))
    nanx = np.vstack([x[0], np.full(1000, np.nan)])
    out = rc._filter(nanx, d, fs)
    ck("a NaN contact stays NaN and spoils nothing else",
       np.isnan(out[1]).all() and np.isfinite(out[0]).all())


def _pool_gmm_agreement():
    """The GMM's verdict says whether its two groups ARE the DS/IED split.

    Built because the first real pool (18 PTEN recordings) gave ΔBIC +881,
    "very strong support for two groups", while those two groups matched the
    DS / IED call at adjusted Rand 0.07 and the split axis had one hump. The
    BIC alone said the opposite of the data.
    """
    from backend import rootcanalpool as pool
    rng = np.random.default_rng(5)
    head("POOL: THE GMM SAYS WHETHER ITS GROUPS ARE THE DS / IED SPLIT")
    mu, sd = np.zeros(3), np.ones(3)

    # Two separate blobs, and the calls ARE the blobs.
    a = rng.normal([-2.5, 0, -2.5], 0.5, size=(300, 3))
    b = rng.normal([2.5, 0, 2.5], 0.5, size=(300, 3))
    Z = np.vstack([a, b])
    calls = ["ds"] * 300 + ["ied"] * 300
    g = pool.gmm_test(Z, mu, sd, calls=calls)
    ck("two blobs that are the two calls: ΔBIC favours two groups",
       g["delta"] is not None and g["delta"] > 10, g["delta"])
    ck("and the agreement is near total",
       g["agree"] and g["agree"]["ari"] > 0.9, g["agree"])
    ck("and the sentence says they match the DS / IED call",
       "match the DS / IED call" in g["verdict"], g["verdict"])

    # ONE skewed cloud, cut in two the way k-means would: by HF.
    z = rng.lognormal(0.0, 0.6, size=(900, 3))
    z = (z - z.mean(axis=0)) / z.std(axis=0)
    cut = np.median(z[:, 2]) + 0.4
    calls = ["ied" if v > cut else "ds" for v in z[:, 2]]
    g = pool.gmm_test(z, mu, sd, calls=calls)
    ck("one skewed cloud still earns two Gaussians by BIC",
       g["delta"] is not None and g["delta"] >= 2, g["delta"])
    ck("but the sentence does not call it two populations",
       "Read the split-axis histogram" in g["verdict"]
       and "match the DS / IED call" not in g["verdict"], g["verdict"])
    ck("graded on the Rand index, not on raw agreement",
       "adjusted Rand" in g["verdict"] and "1 is the same split" in g["verdict"],
       g["verdict"])

    g = pool.gmm_test(Z, mu, sd)
    ck("without calls there is no agreement to report, and no claim about it",
       g["agree"] is None and "DS / IED" not in g["verdict"], g["verdict"])


def _pool_synthetic(A):
    from backend import rootcanalpool as pool
    rng = np.random.default_rng(11)

    head("POOL: CLEAR VS BLUR, ON CLOUDS WHOSE SHAPE IS KNOWN")
    a = _member(pool, "A", "PTEN", 13,
                _blob(rng, 60, 900, 20, 6, "ds")
                + _blob(rng, 30, 2000, 11, 24, "ied"))
    b = _member(pool, "B", "KCNT1", 13,
                _blob(rng, 50, 950, 21, 7, "ds")
                + _blob(rng, 25, 2100, 10, 25, "ied"))
    two = pool.fit_pool([a, b])
    g = two["gmm"]
    ck("two well-separated blobs: dBIC large and positive (%+.1f), very "
       "strong" % g["delta"], g["delta"] > 10
       and g["support"] == "very strong support for two groups"
       and abs(g["delta"] - (g["bic1"] - g["bic2"])) < 1e-6, g)
    ck("the verdict says it is evidence, not proof",
       "evidence, not proof" in g["verdict"]
       and "Gaussian shapes" in g["verdict"], g["verdict"])
    ck("the two components come back in raw units, the higher-HF second",
       len(g["means_raw"]) == 2 and g["means_raw"][1][2] > 20
       and g["means_raw"][0][2] < 10 and abs(sum(g["weights"]) - 1) < 1e-9,
       g["means_raw"])
    truth = [r["truth"] for m in (a, b) for r in m["rows"]]
    agree = np.mean([e["cls_pool"] == tr
                     for e, tr in zip(two["events"], truth)])
    ck("the pooled k-means recovers the blobs (%.0f%%), IED the higher-HF "
       "one" % (100 * agree), agree > 0.95
       and two["centres"][1]["cls"] == "ied"
       and two["centres"][1]["raw"][2] > two["centres"][0]["raw"][2])
    sv = two["split_axis"]["values"]
    ds_s = [v for v, e in zip(sv, two["events"]) if e["cls_pool"] == "ds"]
    ied_s = [v for v, e in zip(sv, two["events"]) if e["cls_pool"] == "ied"]
    ck("the split axis puts DS below 0 and IED above it",
       np.mean(ds_s) < 0 < np.mean(ied_s)
       and len(sv) == len(two["events"]))

    one = pool.fit_pool([
        _member(pool, "C", "PTEN", 1, _blob(rng, 150, 1200, 18, 12, "ds",
                                             sd=(200, 4, 4))),
        _member(pool, "D", "PTEN", 2, _blob(rng, 150, 1200, 18, 12, "ds",
                                             sd=(200, 4, 4)))])
    ck("one blob: dBIC under 2 (%+.1f), no support for two groups"
       % one["gmm"]["delta"], one["gmm"]["delta"] < 2
       and one["gmm"]["support"] == "no support for two groups",
       one["gmm"]["verdict"])

    head("POOL: POOLED RAW UNITS")
    base = _blob(rng, 80, 1000, 18, 10, "ds", sd=(150, 3, 3))
    twin = [dict(r, amp_uV=2 * r["amp_uV"]) for r in base]
    dbl = pool.fit_pool([_member(pool, "E", "PTEN", 3, [dict(r) for r in base]),
                         _member(pool, "F", "PTEN", 4, twin)])
    za = np.array([e["z"][0] for e in dbl["events"]])
    gap = za[80:].mean() - za[:80].mean()
    ck("a member with doubled amplitudes sits higher in the pool (mean z "
       "+%.2f above its twin), where a per-recording z would put them on "
       "top of each other" % gap, gap > 1.5)
    ck("z-scored once, across the whole pool",
       abs(za.mean()) < 1e-9 and abs(za.std() - 1) < 1e-9
       and dbl["params"]["scale"] == "pooled raw")
    ck("the panel's one line says why",
       "differences in size between mice stay visible"
       in dbl["scale"]["why"])

    head("POOL: THE IDENTITY SWITCH, AGAINST A HAND COUNT")
    a2 = dict(a, rows=[dict(r, cls="ds") for r in a["rows"]])
    sw = pool.fit_pool([a2, b])
    ev = sw["events"]
    hand = {"ds": {"ds": 0, "ied": 0}, "ied": {"ds": 0, "ied": 0}}
    for e in ev:
        hand[e["cls_single"]][e["cls_pool"]] += 1
    n_sw = sum(1 for e in ev if e["cls_single"] != e["cls_pool"])
    S = sw["switches"]
    ck("the crosstab is the hand count", S["crosstab"] == hand,
       (S["crosstab"], hand))
    ck("the overall rate is switched / n (%d of %d)" % (n_sw, len(ev)),
       S["switched"] == n_sw and S["n"] == len(ev)
       and abs(S["rate"] - n_sw / float(len(ev))) < 1e-12)
    a_sw = sum(1 for e in ev if e["m"] == 0 and e["switched"])
    rowA = [r for r in S["by_member"] if r["key"] == "A"][0]
    ck("per member: A's every pooled IED is a DS-to-IED switch (%d)" % a_sw,
       rowA["switched"] == a_sw == rowA["ds_to_ied"]
       and rowA["ied_to_ds"] == 0 and a_sw >= 25)
    ck("switched is exactly cls_single != cls_pool, event by event",
       all(e["switched"] == (e["cls_single"] != e["cls_pool"]) for e in ev))

    head("POOL: MICE AND MOUSE TYPES")
    ck("PTEN m13 and KCNT1 m13 are two mice, never one",
       a["mouse_key"] == "PTEN|m13" and b["mouse_key"] == "KCNT1|m13"
       and len(two["switches"]["by_mouse"]) == 2)
    ck("a recording with no mouse number is its own mouse",
       pool.mouse_key("PTEN", None, "s1") == "PTEN|gid:s1")
    ck("types: the cohort as filed, the project prefixed where it is not, "
       "wt from the path, else the project",
       pool.mouse_type_of("PTEN", "PTEN_DKO") == "PTEN_DKO"
       and pool.mouse_type_of("PTEN", "DKO") == "PTEN DKO"
       and pool.mouse_type_of("KCNT1", None,
                              [r"D:\KCNT1\urethane\wt\m2"]) == "KCNT1 wt"
       and pool.mouse_type_of("KCNT1", None, [r"D:\KCNT1\het\m2"]) == "KCNT1")
    ov = pool.fit_pool([a, b], mouse_types={"PTEN|m13": "PTEN het"})
    ck("a mouse_types override wins over the registry",
       ov["members"][0]["mouse_type"] == "PTEN het"
       and ov["members"][0]["mouse_type_default"] == "PTEN"
       and all(e["mouse_type"] == "PTEN het" for e in ov["events"]
               if e["m"] == 0)
       and {r["mouse_type"] for r in ov["switches"]["by_type"]}
       == {"PTEN het", "KCNT1"})

    head("POOL: PARTIAL EVENTS, FOCUS, AND REFUSALS")
    rows = [dict(r) for r in a["rows"]]
    rows[3]["hw_ms"] = None
    pp = pool.fit_pool([dict(a, rows=rows), b])
    e3 = pp["events"][3]
    ck("a 2-axis event is assigned on the axes it has, as in Single",
       e3["partial"] and e3["cls_pool"] in ("ds", "ied") and e3["z"][1] is None
       and pp["counts"]["partial"] == 1 and pp["n_used"] == pp["n"] - 1)
    ck("and has no position on the split axis",
       pp["split_axis"]["values"][3] is None)
    fo = pool.fit_pool([a, b], focus={"mouse_key": "KCNT1|m13"})
    gf = fo["gmm_focus"]
    ck("a focused mouse gets its own 1-vs-2 test, labelled as that mouse's",
       gf and gf["n"] == len(b["rows"]) and "KCNT1|m13" in gf["verdict"]
       and gf["focus"] == {"mouse_key": "KCNT1|m13"})
    ck("and the pool-wide one stays as it was",
       abs(fo["gmm"]["delta"] - two["gmm"]["delta"]) < 1e-9)
    fot = pool.fit_pool([a, b], focus={"mouse_type": "PTEN"})
    ck("a focused mouse TYPE works the same way",
       fot["gmm_focus"]["n"] == len(a["rows"]))
    for bad, what in (([a, dict(b, band=[300.0, 600.0])],
                       "members over different HF bands"),
                      ([a, a], "the same member twice"), ([], "no members")):
        try:
            pool.fit_pool(bad)
            ck("%s are refused with a sentence" % what, False, "accepted")
        except pool.PoolError as exc:
            ck("%s are refused with a sentence" % what,
               str(exc).endswith("."), str(exc))


def _pool_routes(A, tmp, fake):
    from backend import artifacts as artifactsmod
    logs = os.path.join(tmp, "GUI_logs")
    A.ARTIFACTS = artifactsmod.Artifacts(logs, A.STORE)
    c = A.app.test_client()
    bank_before = {r["id"]: len(r.get("versions") or [])
                   for r in A.BANK.all()}

    head("POOL ROUTES (a throwaway artifact store)")
    ck("the rootcanal_pool kind is registered",
       "rootcanal_pool" in artifactsmod.KINDS)
    cj = c.get("/api/rootcanal/pool/candidates").get_json()
    singles = cj.get("singles") or []
    banked = [s for s in singles if s["banked"]]
    unbanked = [s for s in singles if not s["banked"]]
    ck("candidates list banked results and cached reads, each marked",
       cj["ok"] and banked and unbanked
       and all({"key", "entry_id", "session_label", "gid", "project",
                "mouse", "mouse_key", "mouse_type", "n", "banked",
                "version", "params_hash", "read", "here", "counts"}
               <= set(s) for s in singles), cj)
    ck("a recording with both appears twice, as two candidates",
       {s["entry_id"] for s in banked} & {s["entry_id"] for s in unbanked})
    one_b = banked[0]
    fake.calls = 0
    fb = c.post("/api/rootcanal/pool/fit",
                json={"members": [{"key": one_b["key"]}]}).get_json()
    ck("a banked-only pool reads no recording", fb.get("ok")
       and fake.calls == 0, fb.get("error"))
    members = [{"key": s["key"]} for s in singles]
    r = c.post("/api/rootcanal/pool/fit", json={"members": members})
    fit = r.get_json()
    ck("the pool fit answers in the contract's shape",
       r.status_code == 200 and fit.get("ok")
       and {"n", "n_used", "axes", "members", "events", "centres", "rule",
            "scale", "gmm", "gmm_focus", "switches", "split_axis", "counts",
            "params"} <= set(fit)
       and {"m", "i", "t", "amp_uV", "hw_ms", "hf_db", "z", "cls_pool",
            "cls_single", "switched", "partial", "wide", "mouse_key",
            "mouse_type"} <= set(fit["events"][0])
       and {"key", "entry_id", "session_label", "gid", "mouse_key",
            "mouse_type", "banked", "n", "pin"} <= set(fit["members"][0])
       and {"crosstab", "n", "switched", "rate", "by_member", "by_mouse",
            "by_type"} <= set(fit["switches"])
       and {"n", "bic1", "bic2", "delta", "verdict", "weights",
            "means_raw"} <= set(fit["gmm"]),
       fit.get("error") or sorted(fit))
    um = [m for m in fit["members"] if not m["banked"]][0]
    ck("an unbanked member is pinned by read, params and rows digest",
       {"read", "params", "rows_digest"} <= set(um["pin"]))
    bm = [m for m in fit["members"] if m["banked"]][0]
    ck("a banked member is pinned by ds_version and params_hash",
       {"ds_version", "params_hash"} <= set(bm["pin"])
       and bm["pin"]["params_hash"])
    k_ev = [j for j, e in enumerate(fit["events"])
            if fit["members"][e["m"]]["key"] == um["key"]][0]
    body = dict(um["event_body"], i=fit["events"][k_ev]["i"])
    rv = c.post("/api/rootcanal/event", json=body).get_json()
    ck("a dot opens through /api/rootcanal/event with the member's "
       "event_body plus its i", rv.get("ok") and rv["i"] == body["i"],
       rv.get("error"))
    gone = dict(um["event_body"], i=0, read="000000000000")
    rg = c.post("/api/rootcanal/event", json=gone).get_json()
    ck("a member whose read is not here says so in a sentence",
       not rg.get("ok") and "not on this machine" in rg.get("error", ""),
       rg)

    sv = {"members": members, "mouse_types": {}, "note": "check"}
    r = c.post("/api/rootcanal/pool/save", json=dict(sv, nickname="  "))
    ck("saving with an empty label is refused with a sentence",
       r.status_code == 400 and "label" in r.get_json()["error"])
    r = c.post("/api/rootcanal/pool/save", json=dict(sv, nickname="check"))
    s1 = r.get_json()
    ck("a new pool saves as v1 of a new artifact",
       s1.get("ok") and s1["version"] == 1 and not s1["confirmed"]
       and s1["nickname"] == "check"
       and s1["name"].startswith("Root Canal pool · "), s1)
    op = c.get("/api/rootcanal/pool/%s" % s1["artifact_id"]).get_json()
    pay = op.get("payload") or {}
    same = all(_canon_json(pay.get(k)) == _canon_json(fit.get(k))
               for k in ("events", "members", "gmm", "switches", "centres",
                         "split_axis", "counts", "rule", "scale"))
    ck("reopening it gives the identical payload, with no refit",
       op.get("ok") and same and pay.get("pool_key")
       and op["artifact"]["kind"] == "rootcanal_pool")
    r = c.post("/api/rootcanal/pool/save",
               json=dict(sv, nickname="check",
                         artifact_id=s1["artifact_id"]))
    s2 = r.get_json()
    ck("an identical re-save is a confirmation, not a version",
       s2.get("ok") and s2["confirmed"] and s2["version"] == 1, s2)
    r = c.post("/api/rootcanal/pool/save",
               json=dict(sv, members=members[:-1], nickname="check",
                         artifact_id=s1["artifact_id"]))
    s3 = r.get_json()
    ck("a changed member makes v2 of the same pool",
       s3.get("ok") and s3["version"] == 2 and not s3["confirmed"]
       and s3["artifact_id"] == s1["artifact_id"], s3)
    mk = fit["members"][0]["mouse_key"]
    r = c.post("/api/rootcanal/pool/save",
               json=dict(sv, members=members[:-1], nickname="check renamed",
                         mouse_types={mk: "custom type"},
                         artifact_id=s1["artifact_id"]))
    s4 = r.get_json()
    ck("a changed override makes v3, and the label can change with it",
       s4.get("ok") and s4["version"] == 3
       and s4["nickname"] == "check renamed", s4)
    p3 = A.ARTIFACTS.payload(s1["artifact_id"], 3)
    ck("the override is stored in the pool and wins",
       p3["mouse_types"] == {mk: "custom type"}
       and p3["members"][0]["mouse_type"] == "custom type")
    v1 = c.get("/api/rootcanal/pool/%s?version=1"
               % s1["artifact_id"]).get_json()
    ck("an earlier version reopens as it was",
       v1.get("ok") and v1["version"] == 1
       and len(v1["payload"]["members"]) == len(members))
    s5 = c.post("/api/rootcanal/pool/save",
                json=dict(sv, nickname="check")).get_json()
    ck("the same members saved as a new pool are a second pool, on purpose",
       s5.get("ok") and s5["artifact_id"] != s1["artifact_id"])
    pl = c.get("/api/rootcanal/pools").get_json()
    row = [p for p in pl.get("pools") or []
           if p["artifact_id"] == s1["artifact_id"]]
    ck("the shelf lists it with its label, version and member counts",
       pl.get("ok") and len(pl["pools"]) == 2 and row
       and row[0]["nickname"] == "check renamed" and row[0]["version"] == 3
       and row[0]["n_members"] == len(members) - 1
       and row[0]["n_unbanked"] is not None and row[0]["updated"], row)
    head("POOLED BAND AND MARGIN ROUTES (the same throwaway store)")
    unb = [{"key": s["key"]} for s in unbanked]
    fb = c.post("/api/rootcanal/pool/fit",
                json={"members": unb, "band": [600, 900]}).get_json()
    ck("a pool can set its own HF band, and every member is measured on it",
       fb.get("ok") and fb["params"]["band"] == [600.0, 900.0],
       fb.get("error"))
    r = c.post("/api/rootcanal/pool/fit",
               json={"members": unb, "band": [600, 2400]})
    ck("a pooled band past the anti-alias corner is refused",
       r.status_code == 400 and "2000" in r.get_json()["error"])
    ck("the margin kind is registered",
       "rootcanal_margin" in artifactsmod.KINDS)
    ext = {"source": "pool", "members": unb, "k": 2}
    r = c.post("/api/rootcanal/margin/save", json={"extract": ext})
    ck("a margin without a label is refused, with a sentence",
       r.status_code == 400 and "label" in r.get_json()["error"])
    m1 = c.post("/api/rootcanal/margin/save",
                json={"nickname": "chk margin", "extract": ext}).get_json()
    ck("a margin saves with its label", m1.get("ok") and m1["version"] == 1,
       m1.get("error"))
    mg = c.get("/api/rootcanal/margin/%s" % m1["artifact_id"]).get_json()
    ck("and reopens with its centres, scale, measurement and source",
       mg.get("ok") and mg["payload"]["k"] == 2
       and len(mg["payload"]["clusters"]) == 2
       and {"mean", "sd"} <= set(mg["payload"]["scale"])
       and mg["payload"]["measure"]["filter_label"]
       and mg["payload"]["source"]["kind"] == "pool")
    m2 = c.post("/api/rootcanal/margin/save",
                json={"nickname": "chk margin", "extract": ext,
                      "artifact_id": m1["artifact_id"]}).get_json()
    ck("an identical re-save confirms rather than versions",
       m2.get("confirmed") is True and m2["version"] == 1, m2)
    m3 = c.post("/api/rootcanal/margin/save",
                json={"nickname": "chk margin", "artifact_id": m1["artifact_id"],
                      "extract": dict(ext, k=3)}).get_json()
    ck("a changed one is a new version", m3.get("ok") and m3["version"] == 2,
       m3)
    ml = c.get("/api/rootcanal/margins").get_json()
    ck("the margins list it, with k, calls, measurement and source",
       ml.get("ok") and ml["margins"][0]["nickname"] == "chk margin"
       and ml["margins"][0]["k"] == 3 and ml["margins"][0]["source"] == "pool")
    ap = c.post("/api/rootcanal/pool/fit", json={
        "members": unb, "margin": {"artifact_id": m1["artifact_id"],
                                   "version": 1, "mode": "fixed"}}).get_json()
    ck("a pool applies a margin, fixed, and says which",
       ap.get("ok") and ap["margin_used"]["version"] == 1
       and ap["margin_used"]["mode"] == "fixed" and ap["k"] == 2
       and all(cl["call_by"] == "margin" for cl in ap["clusters"]),
       ap.get("error"))
    plain = c.post("/api/rootcanal/pool/fit", json={"members": unb}).get_json()
    ck("and fixed on its own source it is that source's answer",
       [e["cls_pool"] for e in ap["events"]]
       == [e["cls_pool"] for e in plain["events"]])
    r = c.post("/api/rootcanal/pool/fit", json={
        "members": unb, "band": [600, 900],
        "margin": {"artifact_id": m1["artifact_id"], "version": 1}})
    ck("on another band it is refused, naming the difference",
       r.status_code == 400 and "600–900" in r.get_json()["error"],
       r.get_json().get("error"))
    sp = c.post("/api/rootcanal/pool/save", json={
        "nickname": "pool with margin", "members": unb,
        "margin": {"artifact_id": m1["artifact_id"], "version": 1}}).get_json()
    ck("a pool saved with a margin cites that margin version",
       sp.get("ok") and A.ARTIFACTS.cited_by(m1["artifact_id"], 1),
       sp.get("error"))
    dl = c.post("/api/artifacts/%s/delete" % m1["artifact_id"], json={})
    ck("so the margin cannot be deleted from under it",
       dl.status_code >= 400, dl.status_code)

    _saved_elsewhere(A, c, unbanked)

    bank_after = {r["id"]: len(r.get("versions") or [])
                  for r in A.BANK.all()}
    ck("nothing in Pooled wrote to the Event Bank", bank_before == bank_after)


def _saved_elsewhere(A, c, unbanked):
    """As on 2026-10-06: every saved pool had been saved on Strawbarry, and
    opened on another machine its members read there could not be refitted
    -- k, a relabel, a focus, all refused. Here a member's read is taken
    away after the save, as on a machine that never read it."""
    from backend import rootcanal as rc
    head("A SAVED POOL, OPENED WHERE ITS MEMBERS' READS ARE NOT")
    unb = [{"key": u["key"]} for u in unbanked]
    away = unbanked[0]
    meas = {k: v for k, v in rc.measure_of(rc.Params()).items()
            if k != "filter_label"}
    sb = {"members": unb, "k": 3, "cluster_calls": {"0": "ied"},
          "measure": meas}
    sa = c.post("/api/rootcanal/pool/save",
                json=dict(sb, nickname="saved elsewhere")).get_json()
    spay = A.ARTIFACTS.payload(sa["artifact_id"], 1) if sa.get("ok") else {}
    ck("a pool saves at the k and with the calls it was shown with",
       sa.get("ok") and spay.get("k") == 3
       and spay["params"]["cluster_calls"] == {"0": "ied"}, sa)
    src = {"artifact_id": sa["artifact_id"], "version": 1}
    loc2 = c.post("/api/rootcanal/pool/fit",
                  json=dict(sb, k=2, cluster_calls={})).get_json()
    npz = A.ROOTCANAL.cached_path(away["gid"], away["read"], ".npz")
    hid = npz + ".away"
    os.replace(npz, hid)
    try:
        r = c.post("/api/rootcanal/pool/fit", json=sb)
        e = (r.get_json() or {}).get("error") or ""
        ck("without the save, a member read elsewhere is refused by name, "
           "and the refusal says a saved pool would have brought it",
           r.status_code == 400 and away["session_label"] in e
           and "A saved pool brings" in e, e)
        g = c.post("/api/rootcanal/pool/fit",
                   json=dict(sb, saved=src)).get_json()
        fm = [m for m in (g.get("members") or []) if m["key"] == away["key"]]
        ck("opened from the save, it pools, marked as the save's, with no "
           "read here to open", g.get("ok") and fm
           and (fm[0].get("from_saved") or {}).get("version") == 1
           and fm[0]["here"] is False and fm[0]["event_body"] is None,
           g.get("error"))
        evk = lambda res: [(x["m"], x["i"], x["cls_pool"], x["cls_single"])
                           for x in res["events"]]
        ck("and the answer is the saved answer, event for event",
           g.get("ok") and evk(g) == evk(spay)
           and abs(g["gmm"]["delta"] - spay["gmm"]["delta"]) < 1e-9)
        spin = [m for m in spay["members"] if m["key"] == away["key"]][0]
        ck("its numbers are the ones its pin names",
           fm and fm[0]["pin"]["rows_digest"] == spin["pin"]["rows_digest"])
        g2 = c.post("/api/rootcanal/pool/fit",
                    json=dict(sb, saved=src, k=2, cluster_calls={})).get_json()
        ck("another k works on its numbers, its own call recomputed at that "
           "k -- the same as where its read is",
           g2.get("ok") and loc2.get("ok") and evk(g2) == evk(loc2),
           g2.get("error"))
        g3 = c.post("/api/rootcanal/pool/fit", json=dict(
            sb, saved=src, focus={"mouse_key": fm[0]["mouse_key"]})).get_json()
        ck("a focus on its mouse works", g3.get("ok") and g3.get("gmm_focus"),
           g3.get("error"))
        mine = [[away["key"], x["i"]] for x in g["events"]
                if g["members"][x["m"]]["key"] == away["key"]][:3]
        g4 = c.post("/api/rootcanal/pool/fit", json=dict(
            sb, saved=src, drawn=[{"events": mine, "call": "ds"}])).get_json()
        ck("and a cluster drawn round its dots",
           g4.get("ok") and any(cl["call_by"] == "drawn" and cl["n"] == 3
                                for cl in g4["clusters"]), g4.get("error"))
        r = c.post("/api/rootcanal/pool/fit", json=dict(
            sb, saved=src, measure=dict(meas, filt="ds")))
        e = (r.get_json() or {}).get("error") or ""
        ck("measuring it another way is refused, naming it and the change",
           r.status_code == 400 and away["session_label"] in e
           and "Asked for DS filter" in e, e)
        ga = c.post("/api/rootcanal/pool/group", json=dict(
            sb, saved=src, events=mine)).get_json()
        ck("its average says its read is not here",
           not ga.get("ok") and "reads are on this machine" in (ga.get("error")
                                                                or ""),
           ga)
        sv2 = c.post("/api/rootcanal/pool/save", json=dict(
            sb, saved=src, k=2, cluster_calls={}, nickname="saved elsewhere",
            artifact_id=sa["artifact_id"])).get_json()
        ins = ((A.ARTIFACTS.get(sa["artifact_id"]) or {}).get("versions")
               or [{}])[-1].get("inputs") or []
        pin = [x for x in ins if x.get("key") == away["key"]]
        ck("saved again here, its pin says its numbers came from v1",
           sv2.get("ok") and sv2["version"] == 2 and pin
           and pin[0].get("from_saved") == src, sv2)
    finally:
        os.replace(hid, npz)
    # A pool saved before the measurement was recorded: it reopens with
    # the one its members were pinned with.
    old = dict(spay, params={k: v for k, v in spay["params"].items()
                             if k != "measure"})
    subj = dict((A.ARTIFACTS.get(sa["artifact_id"]) or {}).get("subject")
                or {}, pool_key="old-" + sa["artifact_id"])
    oa = A.ARTIFACTS.create("rootcanal_pool", subj, old,
                            params=old["params"], nickname="old pool")
    og = c.get("/api/rootcanal/pool/%s" % oa["id"]).get_json()
    want = rc.measure_of(rc.Params(**A._rootcanal_fit_part(
        spay["members"][0]["pin"]["params"])))
    ck("a pool saved without its measurement reopens with its members'",
       og.get("ok") and og["payload"]["params"].get("measure") == want
       and og["payload"]["params"].get("measure_from_pins") is True,
       (og.get("payload") or {}).get("params"))


def _real_pool(A):
    head("A REAL POOL: every Root Canal single on this machine")
    from backend import rootcanalpool as pool
    t0 = time.time()
    cands = A._rootcanal_pool_candidates()
    if not cands:
        print("  skipped: no Root Canal singles on this machine")
        return
    members = A._rootcanal_pool_members([{"key": c["key"]} for c in cands])
    res = pool.fit_pool(members, focus={"mouse_key": "PTEN|m13"})
    g, sw = res["gmm"], res["switches"]
    print("  %d singles (%d banked), %d events, %d mice, %.0f s"
          % (len(cands), sum(1 for c in cands if c["banked"]), res["n"],
             len({m["mouse_key"] for m in members}), time.time() - t0))
    print("  counts %s" % res["counts"])
    print("  rule: %s" % res["rule"])
    print("  pool-wide: %s" % g["verdict"])
    if g.get("weights"):
        for w, mr in zip(g["weights"], g["means_raw"]):
            print("    component w=%.3f  amp %.0f uV, hw %.1f ms, HF %+.1f dB"
                  % (w, mr[0], mr[1], mr[2]))
    if res["gmm_focus"]:
        print("  focus: %s" % res["gmm_focus"]["verdict"])
    print("  identity switch: %d of %d (%.1f%%), crosstab %s"
          % (sw["switched"], sw["n"], 100 * (sw["rate"] or 0),
             sw["crosstab"]))
    for r in sw["by_mouse"]:
        print("    %-12s %4d events, %3d switched (%.0f%%)"
              % (r["mouse_key"], r["n"], r["switched"],
                 100 * (r["rate"] or 0)))
    ck("the real pool fits", res["n"] > 0 and g["n"] > 0)
    ck("no event's HF is a flat-window infinity",
       max(e["hf_db"] for e in res["events"] if e["hf_db"] is not None)
       < 80)


if __name__ == "__main__":
    raise SystemExit(main())
