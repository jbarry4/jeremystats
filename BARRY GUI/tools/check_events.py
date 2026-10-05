"""Checks for backend/monoevents.py, the Monolith's event-first route.

A made-up cue session is written as real .ncs files (4 kHz, every region's
first wire): P300-like bumps, each with a 6 Hz burst, planted in Right DHC at known times -- one 0.4 s
into every cue 1, and one in every other inter-trial interval -- echoed 40 ms
later in Right ACC (its burst a fixed phase behind) and nowhere else; a clipped stretch with a large
deflection in it; and band-limited noise everywhere. Then:

  * every planted event is found, to 60 ms (the noise moves a broad peak
    that much), and next to nothing else;
  * the clipped deflection is not an event;
  * each is placed in its window, and the histogram peaks just after cue 1;
  * Right ACC moved with them (size and phase beyond random times) and
    Right OFC did not -- the control;
  * a region histology rules out is said to be, not computed;
  * settings outside their ranges are refused;
  * the report pools a rat-day as itself.

Usage: python tools/check_events.py
"""
import os
import shutil
import struct
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import coupling, nlx                      # noqa: E402
from backend import monolith as MO                     # noqa: E402
from backend import monoevents as EV                   # noqa: E402

N = {"ok": 0, "bad": 0}


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print("  %s  %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else "   [%s]" % (detail,)))


FS_RAW = 4000.0
ADBV = 0.000000030517578125
DUR = 700.0
OPENERS = [60.0 + 50.0 * k for k in range(12)]


def write_ncs(path, x_uv, chan, fs=FS_RAW, t0_us=1000000):
    head = ("######## Neuralynx Data File Header\n-FileType CSC\n-AcqEntName CSC%d\n"
            "-SamplingFrequency %.4f\n-ADBitVolts %.24f\n-ADMaxValue 32767\n"
            "-AcquisitionSystem AcqSystem1 DigitalLynxSX\n-ApplicationName Cheetah 6.4.2\n") % (chan, fs, ADBV)
    raw = head.encode("latin-1")
    raw += b"\x00" * (nlx.HEADER_BYTES - len(raw))
    # The reader negates (the lab's inverted polarity): store -x.
    counts = np.clip(np.round(-x_uv / (ADBV * 1e6)), -32767, 32767).astype(np.int16)
    n = nlx.SAMPLES_PER_RECORD
    nrec = counts.size // n
    per_us = n / fs * 1e6
    rec = np.zeros(nrec, dtype=nlx.RECORD_DTYPE)
    rec["timestamp"] = np.round(t0_us + np.arange(nrec) * per_us).astype(np.uint64)
    rec["channel"] = chan
    rec["freq"] = int(round(fs))
    rec["nvalid"] = n
    rec["samples"] = counts[:nrec * n].reshape(nrec, n)
    with open(path, "wb") as fh:
        fh.write(raw)
        fh.write(rec.tobytes())


def bump(t, at, amp, sd=0.16):
    return amp * np.exp(-0.5 * ((t - at) / sd) ** 2)


def theta(t, at, phase, amp=25.0, hz=6.0, sd=0.15):
    k = np.abs(t - at) < 4 * sd
    out = np.zeros_like(t)
    out[k] = amp * np.exp(-0.5 * ((t[k] - at) / sd) ** 2) * np.cos(2 * np.pi * hz * (t[k] - at) + phase)
    return out


def make_session(folder, seed=3):
    from scipy.signal import butter, sosfiltfilt
    rng = np.random.default_rng(seed)
    n = int(DUR * FS_RAW)
    t = np.arange(n) / FS_RAW
    sos = butter(4, [1.0 / (FS_RAW / 2), 15.0 / (FS_RAW / 2)], btype="bandpass", output="sos")
    planted = [a + 0.4 for a in OPENERS] + [a + 35.0 for k, a in enumerate(OPENERS) if k % 2 == 0]
    planted = sorted(planted)
    names = list(coupling.dewey_map())
    for name in names:
        x = sosfiltfilt(sos, rng.standard_normal(n))
        x = 30.0 * x / x.std() + 8.0 * rng.standard_normal(n)
        if name == "Right DHC":
            for at in planted:
                x += bump(t, at, 420.0) + theta(t, at, 0.0)
            # A clipped stretch with a big deflection in it, between
            # presentations 1 and 2: never an event.
            x += bump(t, 145.0, 900.0)
            k = (t >= 144.98) & (t < 145.03)
            x[k] = 1000.0
        if name == "Right ACC":
            for at in planted:
                x += bump(t, at + 0.04, 250.0) + theta(t, at, -0.8)
        write_ncs(os.path.join(folder, "CSC%d.ncs" % coupling.dewey_map()[name][0]), x, coupling.dewey_map()[name][0])
    return planted


def fake_day(folder, day="Precon1"):
    units = [{"id": "p%02d" % (k + 1), "pair": {"opener_t": a, "closer_t": a + 10.0, "offset_t": a + 20.0}}
             for k, a in enumerate(OPENERS)]
    return {"rat": 99, "day": day, "folders": [{"role": "SPC", "local": folder}], "bad": [],
            "blocked": {"Right POR": "histology: not there"}, "units": units}


def routes():
    """The routes, read only, on whatever Monolith this machine has: a
    report (or a refusal when there is none), refusals of bad settings, and
    no run without confirm. Nothing is started."""
    print("\nThe routes (read only)")
    from backend import app as appmod
    c = appmod.app.test_client()
    r = c.get("/api/arc/monolith/events")
    j = r.get_json()
    check("the report: what is done for the defaults, or no manifest said",
          (r.status_code == 200 and j["params"] == EV.DEFAULTS and len(j["days"]) == j["todo"] + sum(1 for d in j["days"] if d["done"]))
          or (r.status_code == 404 and "manifest" in j["error"]), (r.status_code, j.get("error")))
    r.close()
    r = c.get("/api/arc/monolith/events?z=1")
    check("settings out of range are refused", r.status_code in (400, 404), r.status_code)
    r.close()
    r = c.post("/api/arc/monolith/events", json={})
    check("no run without confirm", r.status_code == 400, r.status_code)
    r.close()
    r = c.get("/api/arc/monolith/events/example?rat=x&day=Precon1&i=0")
    check("an example needs whole numbers", r.status_code in (400, 404), r.status_code)
    r.close()


def main():
    work = tempfile.mkdtemp(prefix="zz-events-")
    try:
        MO.configure(os.path.join(work, "logs"))
        folder = os.path.join(work, "spc")
        os.makedirs(folder)
        print("Writing a made-up cue session (12 regions, %d s, 4 kHz)" % DUR)
        planted = make_session(folder)
        p = EV.params_of({})
        day = fake_day(folder)
        print("\nFinding the events")
        got = EV.run_day(day, p)
        check("it ran on the hippocampal wire", got.get("wire") == coupling.dewey_map()["Right DHC"][0], got.get("why"))
        ev = [e["t"] for e in got.get("events") or []]
        hit = [any(abs(e - a) <= 0.06 for e in ev) for a in planted]
        extra = [e for e in ev if not any(abs(e - a) <= 0.06 for a in planted)]
        check("every planted event found, to 60 ms (%d of %d)" % (sum(hit), len(planted)), all(hit),
              [a for a, h in zip(planted, hit) if not h])
        check("and next to nothing else (%d extra)" % len(extra), len(extra) <= 2, extra)
        check("the clipped deflection is not an event", not any(140.0 <= e <= 150.0 for e in ev), [e for e in ev if 140 <= e <= 150])
        check("the rail costs its guard, not the session (%.1f s usable of %.1f)" % (got["usable_s"], got["span"][1] - got["span"][0]),
              got["span"][1] - got["span"][0] - 1.0 < got["usable_s"] < got["span"][1] - got["span"][0])
        T = got["timing"]
        check("placed in its window: 12 in cue 1, 6 between presentations", T["counts"]["cue1"] == 12 and T["counts"]["iti"] == 6
              and T["counts"]["pre"] == 0 and T["counts"]["cue2"] == 0 and T["counts"]["post"] == 0, T["counts"])
        ps = T["psth"]["rate_per_min"]
        k0 = int((0 - EV.PSTH_FROM) // EV.PSTH_BIN)
        check("the histogram peaks in the first second of cue 1 (60 a minute)", int(np.argmax(ps)) == k0 and abs(ps[k0] - 60.0) < 1e-9, ps[k0 - 1:k0 + 2])
        R = got["regions"]
        acc, ofc = R["Right ACC"], R["Right OFC"]
        check("Right ACC moved with them: bigger than random times (z %.1f, p %.4f)" % (acc["z_size"], acc["p_size"]),
              acc["p_size"] <= 0.01 and acc["z_size"] > 3, acc)
        check("and in phase with the hippocampus (PLV %.2f vs %.2f at random times, p %.4f)" % (acc["plv"], acc["plv_random"], acc["p_plv"]),
              acc["p_plv"] <= 0.01, acc.get("p_plv"))
        check("CONTROL: Right OFC did not (size p %.3f, phase p %.3f)" % (ofc["p_size"], ofc["p_plv"]),
              ofc["p_size"] > 0.05 and ofc["p_plv"] > 0.05, ofc)
        check("the event-locked average of Right ACC peaks 40 ms after the event",
              abs((int(np.nanargmax(acc["erp"])) - (len(acc["erp"]) - 1) // 2) * (1000.0 / EV.OUT_FS) - 40.0) <= 10.0)
        check("a region histology rules out is said to be, not computed", R["Right POR"].get("why") == "histology rules it out")
        print("\nThe band's low edge")
        x, ok = EV.read_span(os.path.join(folder, "CSC%d.ncs" % coupling.dewey_map()["Right DHC"][0]),
                             nlx.recording_start_us(folder), got["span"][0], got["span"][1])
        loose = dict(p, min_ms=20.0, max_ms=3000.0)
        e05, _m, _s = EV.detect(x, ok, loose, t0=got["span"][0])
        e10, _m, _s = EV.detect(x, ok, dict(loose, low=1.0), t0=got["span"][0])
        w05, w10 = np.median([e["width_ms"] for e in e05]), np.median([e["width_ms"] for e in e10])
        z05, z10 = np.median([e["z"] for e in e05]), np.median([e["z"] for e in e10])
        check("why 0.5 Hz: a 1 Hz edge shrinks a 380 ms deflection (median width %.0f vs %.0f ms, z %.1f vs %.1f)"
              % (w10, w05, z10, z05), w10 < 0.7 * w05 and z10 < 0.8 * z05 and w05 >= 150.0, (w05, w10, z05, z10))
        print("\nSettings")
        bad = 0
        for raw in ({"z": 1}, {"region": "Nowhere"}, {"low": 5, "high": 6}, {"min_ms": 600, "max_ms": 500}, {"zmax": 4.5}):
            try:
                EV.params_of(raw)
            except EV.EventsError:
                bad += 1
        check("settings outside their ranges are refused (5 of 5)", bad == 5, bad)
        check("the same settings give the same cache, others another",
              EV.digest(EV.params_of({})) == EV.digest(EV.params_of({"z": 4})) != EV.digest(EV.params_of({"z": 5})))
        print("\nThe report")
        MO._write_json(EV._cache_path(p, 99, "Precon1"), got)
        man = {"days": [day, fake_day(folder, "Precon4")]}
        rep = EV.report(p, man)
        check("one rat-day done, one to do", rep["todo"] == 1 and [d["done"] for d in rep["days"]] == [True, False])
        P1 = rep["pooled"]["Precon1"]
        check("pooled over one rat, it is that rat", P1["rats"] == 1 and P1["events"] == len(ev)
              and P1["regions"]["Right ACC"]["size_rats"] == 1 and P1["regions"]["Right OFC"]["size_rats"] == 0
              and abs(P1["psth"]["mean"][k0] - 60.0) < 1e-6, P1["regions"]["Right ACC"])
        ex = EV.example(p, man, 99, "Precon1", 0)
        check("an example event: every region's trace around it", len(ex["rows"]) == 12
              and sum(1 for r in ex["rows"] if r.get("raw")) == 11 and len(ex["rows"][0]["raw"]) == int(2 * 2.0 * EV.OUT_FS) + 1,
              [r.get("why") for r in ex["rows"]])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    routes()
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    return 1 if N["bad"] else 0


if __name__ == "__main__":
    sys.exit(main())
