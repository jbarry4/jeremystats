# -*- coding: utf-8 -*-
"""Check The Arc's transition windows against real data.

    python tools/check_arc_transition.py                 J4 Precon1, J7 Precon2
    python tools/check_arc_transition.py <gid> [<gid>]   those recordings
    python tools/check_arc_transition.py --quick         skip the slow parts

Run it from PowerShell. What it checks, on real banked DEWEY recordings read
off E:, and nothing it checks writes to the Event Bank:

  1. ONE READ. `spark.clipping_both` reads each channel's samples once per
     cue pair for both kinds of window -- counted, not assumed -- and the
     same measurement done as two passes reads them twice. Timed both ways.
  2. STATE UNCHANGED. The state half of the combined read is the same
     answer, channel for channel and number for number, as the clipping
     code before transitions existed (a copy of it is kept beside this file
     as `_spark_state_reference.py` -- see REFERENCE below).
  3. TRANSITION = A DIRECT MEASUREMENT. Every transition window of every
     pair on every channel is measured again, independently: cut to the
     sample by Coupling's own reader (`coupling._window_block`, which walks
     the record timestamps its own way), run through the same detector, and
     graded by 50 ms at the rail. Every hit count and every lost/kept
     verdict has to agree.
  4. THE ROUTES, through Flask's test client with `BANK.add` replaced by a
     function that keeps what it was handed: the clipping route returns
     both measurements and refuses bad lengths with a sentence; the bank
     route writes the transition clipping into the SAME `clipped` dict and
     records `state_measured`, `transition_measured` and the lengths.
  5. COUPLING, KIND = TRANSITION. A transition run on the real banked entry
     (which predates transitions) is refused with a sentence naming Spark.
     A run on the entry the bank route WOULD have written is made end to
     end, and every region's one wire in every transition window is the
     lowest-numbered wire not excluded there and not bad.
  6. STATE COUPLING UNCHANGED, on one pair, against the pre-change engine.

Every important check is negative-controlled: the thing is broken on
purpose and the check is shown to fail.

REFERENCE. `_spark_state_reference.py` is the state clipping loop exactly as
it stood before transition windows were added (2026-09-27). It exists only
so check 2 has something independent to compare against; nothing imports it
but this file.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

import numpy as np                                        # noqa: E402

RESULTS = {"ok": 0, "fail": 0}


def check(name, cond, detail=""):
    RESULTS["ok" if cond else "fail"] += 1
    print(("ok    " if cond else "FAIL  ") + name
          + ("" if cond or not detail else "   [%s]" % detail))
    return cond


def note(msg):
    print("      " + msg)


def head(msg):
    print("\n== " + msg)


def load_reference():
    path = os.path.join(HERE, "_spark_state_reference.py")
    spec = importlib.util.spec_from_file_location("backend._spark_ref", path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "backend"
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# The direct measurement, written apart from spark.py on purpose
# --------------------------------------------------------------------------
def direct_transition(folder, pairs, before_s, after_s, skip, spark, coupling,
                      nlx, shift_s=0.0, rule="time"):
    """{pair_id: {csc: {window: (hits, lost)}}}, measured window by window.

    Cut by `coupling._window_block` -- the reader Coupling itself analyses
    with -- from exactly [boundary - before, boundary + after]. `shift_s`
    and `rule` exist for the negative controls: a window in the wrong place,
    or graded as a fraction instead of in time, must disagree.
    """
    origin = nlx.recording_start_us(folder)
    out = {}
    files = [(n, p) for n, p in nlx.list_csc_files(folder, even_only=False)
             if int(n) not in set(skip)]
    for num, path in files:
        hdr = nlx.read_header(path)
        fs = float(hdr.get("SamplingFrequency") or 32000.0)
        admax = float(hdr.get("ADMaxValue") or 32767.0)
        n_rec = (os.path.getsize(path) - nlx.HEADER_BYTES) \
            // nlx.RECORD_DTYPE.itemsize
        mm = np.memmap(path, dtype=nlx.RECORD_DTYPE, mode="r",
                       offset=nlx.HEADER_BYTES, shape=(int(n_rec),))
        try:
            for p in pairs:
                o, c, e = p["opener_t"], p["closer_t"], p["offset_t"]
                for name, at in (("onset", o), ("switch", c), ("offset", e)):
                    t0 = at - before_s + shift_s
                    t1 = at + after_s + shift_s
                    block, why = coupling._window_block(mm, n_rec, fs, origin,
                                                        t0, t1)
                    if block is None:
                        out.setdefault(p["pair_id"], {}).setdefault(
                            int(num), {})[name] = (None, why)
                        continue
                    hits, _run, _sp = spark._clip_runs(
                        block, admax * spark.CLIP_FRACTION, spark.CLIP_MIN_RUN)
                    if rule == "time":
                        lost = hits * 1000.0 / fs >= 50.0
                    else:
                        lost = hits / float(block.size) >= 0.005
                    out.setdefault(p["pair_id"], {}).setdefault(
                        int(num), {})[name] = (int(hits), bool(lost))
        finally:
            del mm
    return out


def compare_transition(measured, direct, pairs):
    """(n_windows_compared, [disagreements])."""
    bad, n = [], 0
    for p in pairs:
        pid = p["pair_id"]
        got = (measured.get(pid) or {})
        want = (direct.get(pid) or {})
        for csc in sorted(set(got) | set(want)):
            for w in ("onset", "switch", "offset"):
                dv = (want.get(csc) or {}).get(w)
                if dv is None:
                    dv = (0, False)
                if dv[0] is None:
                    # Coupling's reader refused this window; the combined
                    # read must have said it was unmeasured, not clean.
                    um = ((got.get(csc) or {}).get("unmeasured") or {})
                    n += 1
                    if w not in um:
                        bad.append((pid, csc, w, "direct refused: %s" % dv[1],
                                    "measured says nothing"))
                    continue
                d = ((got.get(csc) or {}).get("detail") or {}).get(w)
                g = (0, False) if d is None else (int(d["n"]), bool(d["lost"]))
                gl = w in ((got.get(csc) or {}).get("windows") or [])
                n += 1
                if g != dv or gl != dv[1]:
                    bad.append((pid, csc, w, dv, g))
    return n, bad


def strip_stats(by_pair):
    return json.loads(json.dumps(by_pair, sort_keys=True, default=str))


# --------------------------------------------------------------------------
def main(argv):
    quick = "--quick" in argv
    gids = [a for a in argv if not a.startswith("--")]

    t = time.time()
    from backend import app as A
    from backend import coupling, nlx, spark
    note("app imported in %.1f s" % (time.time() - t))
    ref = load_reference()

    banked = A._spark_banked()
    if not gids:
        # J4 Precon1 (histology known, four probes elsewhere) and J7 Precon2.
        want = ("DEWEY r4 s1 Precon1", "DEWEY r7 s2 Precon2")
        for g, b in banked.items():
            if any(str(b.get("name") or "").startswith(w) for w in want):
                gids.append(g)
        gids.sort(key=lambda g: banked[g]["name"])
    if not gids:
        print("no banked recording to check against")
        return 2

    for gi, gid in enumerate(gids):
        sm, got = A._spark_read(gid)
        folder = got["path"]
        pairs = got["pairs"]
        bad = sorted(int(c) for c in (sm.get("bad_channels") or []))
        head("%s  (%s)  %d pairs, bad %s" % (sm.get("label"), gid, len(pairs),
                                             bad or "none"))

        # ---------------- 1. one read ----------------
        stats = {}
        t = time.time()
        both = spark.clipping_both(folder, pairs, skip=bad, stats=stats)
        t_both = time.time() - t
        n_ch = stats["channels"]
        note("combined read: %.2f s, %d channels x %d pairs, %d slices, "
             "%.1f MB" % (t_both, n_ch, len(pairs), stats["reads"],
                          stats["bytes"] / 1e6))
        check("one slice per channel per pair, for both kinds",
              stats["reads"] == n_ch * len(pairs),
              "%d slices for %d x %d" % (stats["reads"], n_ch, len(pairs)))
        check("  the transition half was measured",
              both["transition"]["measured"] is True,
              both["transition"].get("why"))

        # The same measurement as two passes, which is what one read saves.
        s2, s3 = {}, {}
        t = time.time()
        st_only = spark._measure(folder, pairs, skip=bad, kinds=("state",),
                                 stats=s2)
        t_s = time.time() - t
        t = time.time()
        tr_only = spark._measure(folder, pairs, skip=bad,
                                 kinds=("transition",), stats=s3)
        t_t = time.time() - t
        note("two passes: state %.2f s + transition %.2f s = %.2f s, %d "
             "slices, %.1f MB" % (t_s, t_t, t_s + t_t,
                                  s2["reads"] + s3["reads"],
                                  (s2["bytes"] + s3["bytes"]) / 1e6))
        check("NEGATIVE CONTROL: two passes read twice, and the one-read "
              "check would catch it",
              s2["reads"] + s3["reads"] == 2 * n_ch * len(pairs)
              and s2["reads"] + s3["reads"] != n_ch * len(pairs))
        check("  and two passes give the same two answers",
              strip_stats(st_only["state"]["by_pair"])
              == strip_stats(both["state"]["by_pair"])
              and strip_stats(tr_only["transition"]["by_pair"])
              == strip_stats(both["transition"]["by_pair"]))

        # ---------------- 2. state unchanged ----------------
        t = time.time()
        old_pp, old_pc = ref.clipping_for(folder, pairs, skip=bad)
        t_old = time.time() - t
        note("the pre-transition state code: %.2f s (four slices a pair)"
             % t_old)
        new_pp, new_pc = spark.clipping_for(folder, pairs, skip=bad)
        check("state clipping is the same answer as before transitions",
              strip_stats(old_pp) == strip_stats(new_pp)
              and old_pc == new_pc)
        check("  and the combined read's state half is that answer too",
              strip_stats(old_pp) == strip_stats(both["state"]["by_pair"]))
        n_state_lost = sum(len(d["windows"]) for ch in old_pp.values()
                           for d in ch.values())
        note("state windows lost: %d" % n_state_lost)
        # Negative control: one channel's one window flipped.
        broken = copy.deepcopy(new_pp)
        for pid, ch in broken.items():
            if ch:
                c = sorted(ch)[0]
                ch[c]["windows"] = (ch[c]["windows"] or []) + ["pre"]
                ch[c]["n_flip"] = 1
                break
        check("NEGATIVE CONTROL: a state answer with one window changed is "
              "caught", strip_stats(old_pp) != strip_stats(broken))
        check("the summary grades on four windows",
              all(r["windows_total"] == 4 * len(pairs)
                  for r in spark.clip_summary(new_pp, len(pairs))))
        check("  and the transition summary on three",
              all(r["windows_total"] == 3 * len(pairs)
                  for r in spark.clip_summary(
                      both["transition"]["by_pair"], len(pairs), 3)))

        # ---------------- 3. transition = direct ----------------
        tb = both["transition"]
        t = time.time()
        direct = direct_transition(folder, pairs, tb["before_s"],
                                   tb["after_s"], bad, spark, coupling, nlx)
        note("direct, window-by-window measurement: %.2f s" % (time.time() - t))
        n, dis = compare_transition(tb["by_pair"], direct, pairs)
        n_lost = sum(1 for ch in direct.values() for ws in ch.values()
                     for v in ws.values() if v[0] is not None and v[1])
        n_touch = sum(1 for ch in direct.values() for ws in ch.values()
                      for v in ws.values() if v[0])
        note("%d transition windows compared: %d touched the rail, %d lost"
             % (n, n_touch, n_lost))
        check("every transition window agrees with a direct measurement of "
              "exactly that window", not dis and n > 0,
              "%d disagree, first %s" % (len(dis), dis[:3]))
        check("  and there is something to agree about (the check is live)",
              n_lost > 0 or n_touch > 0,
              "no transition window touched the rail on this recording")
        if not quick:
            shifted = direct_transition(folder, pairs, tb["before_s"],
                                        tb["after_s"], bad, spark, coupling,
                                        nlx, shift_s=0.5)
            _n, dis2 = compare_transition(tb["by_pair"], shifted, pairs)
            check("NEGATIVE CONTROL: the same windows moved by half a second "
                  "disagree", len(dis2) > 0, "moved windows agreed everywhere")
            frac = direct_transition(folder, pairs, tb["before_s"],
                                     tb["after_s"], bad, spark, coupling,
                                     nlx, rule="frac")
            _n, dis3 = compare_transition(tb["by_pair"], frac, pairs)
            note("graded as half a percent of 3 s instead of 50 ms: %d "
                 "verdicts would change" % len(dis3))
            if gi == 0:
                check("NEGATIVE CONTROL: grading by fraction instead of in "
                      "time changes verdicts somewhere",
                      len(dis3) > 0 or n_touch == 0,
                      "no window sits between 15 and 50 ms at the rail here")

        # ---------------- 4 + 5. routes ----------------
        routes(A, gid, sm, got, both, bad, quick and gi > 0)

        # ---------------- 6. state coupling unchanged ----------------
        if not quick and gi == 0:
            state_coupling_unchanged(A, gid, sm)

    print("\n%d passed, %d failed" % (RESULTS["ok"], RESULTS["fail"]))
    return 1 if RESULTS["fail"] else 0


# --------------------------------------------------------------------------
# Routes, with the bank's writer replaced
# --------------------------------------------------------------------------
def routes(A, gid, sm, got, both, bad, light=False):
    from backend import coupling, nlx, spark
    head("routes for %s" % sm.get("label"))
    client = A.app.test_client()
    base = "/api/arc/spark/" + gid

    r = client.post(base + "/clipping", json={"before_s": 7, "after_s": 2})
    check("a before-length past 5 s is refused, with a sentence",
          r.status_code == 400 and "between" in (r.get_json() or {}).get(
              "error", ""), r.get_data(as_text=True)[:160])
    r = client.post(base + "/clipping", json={"before_s": 0.3,
                                              "after_s": 0.4})
    check("a window shorter than one second in all is refused",
          r.status_code == 400 and "one-second" in (r.get_json() or {}).get(
              "error", ""), r.get_data(as_text=True)[:160])
    r = client.post(base + "/clipping", json={"before_s": "abc"})
    check("a length that is not a number is refused",
          r.status_code == 400, r.get_data(as_text=True)[:160])

    r = client.post(base + "/clipping", json={"again": True})
    j = r.get_json() or {}
    check("the clipping route answers", r.status_code == 200 and j.get("ok"),
          r.get_data(as_text=True)[:200])
    tr = j.get("transition") or {}
    check("  with both measurements",
          j.get("state_measured") is True and tr.get("measured") is True
          and tr.get("windows") == ["onset", "switch", "offset"]
          and j.get("windows") == ["pre", "cue1", "cue2", "post"])
    check("  the transition half is the combined read's",
          strip_stats(tr.get("by_pair")) == strip_stats(
              {str(k): v for k, v in both["transition"]["by_pair"].items()}))
    check("  the state half is unchanged",
          strip_stats(j.get("by_pair")) == strip_stats(
              {str(k): v for k, v in both["state"]["by_pair"].items()}))
    check("  and it says the file was read once",
          (j.get("read") or {}).get("slices") == (j.get("read") or {}).get(
              "channels", -1) * len(got["pairs"]), j.get("read"))
    check("  bad channels are skipped for transitions too",
          not any(int(c) in set(bad) for ch in (tr.get("by_pair") or {}).values()
                  for c in ch))

    # ---- the bank route, with the writer captured ----
    kept = {}
    real_add = A.BANK.add

    def fake_add(entry):
        kept["entry"] = copy.deepcopy(entry)
        return {"id": entry.get("id") or "captured", "version": -1,
                "events": entry.get("events")}
    A.BANK.add = fake_add
    try:
        r = client.post(base + "/bank", json={"excluded": {}})
    finally:
        A.BANK.add = real_add
    check("the bank route files (to a captured writer, not the bank)",
          r.status_code == 200 and "entry" in kept,
          r.get_data(as_text=True)[:200])
    e = kept.get("entry") or {}
    prm = e.get("parameters") or {}
    check("  source parameters record both measurements and the lengths",
          prm.get("state_measured") is True
          and prm.get("transition_measured") is True
          and prm.get("clip_measured") is True
          and prm.get("transition_before_s") == 1.0
          and prm.get("transition_after_s") == 2.0
          and prm.get("clip_pad_s") == spark.CLIP_PAD_S, prm)
    want = {}
    for pid, ch in both["transition"]["by_pair"].items():
        for c, d in ch.items():
            for w in d["windows"]:
                want.setdefault(pid, {}).setdefault(w, set()).add(int(c))
    ok = True
    for i, ev in enumerate(e.get("events") or [], start=1):
        cl = ev.get("clipped") or {}
        for w in ("onset", "switch", "offset"):
            if set(cl.get(w) or []) != (want.get(i) or {}).get(w, set()):
                ok = False
    check("  transition clipping lands in the SAME clipped dict, by window",
          ok and any(want.values()) or (ok and not want))
    n_t_keys = sum(1 for ev in (e.get("events") or [])
                   for w in (ev.get("clipped") or {})
                   if w in ("onset", "switch", "offset"))
    note("%d transition window lists written onto %d events"
         % (n_t_keys, len(e.get("events") or [])))
    st_ok = True
    for i, ev in enumerate(e.get("events") or [], start=1):
        cl = ev.get("clipped") or {}
        for w in ("pre", "cue1", "cue2", "post"):
            exp = sorted(int(c) for c, d in
                         (both["state"]["by_pair"].get(i) or {}).items()
                         if w in d["windows"])
            if sorted(cl.get(w) or []) != exp:
                st_ok = False
    check("  and the state windows are written exactly as before", st_ok)

    # A by-hand transition decision travels too.
    A.BANK.add = fake_add
    try:
        client.post(base + "/bank", json={"excluded": {
            "1": {"onset": [99], "pre": [98]}}})
    finally:
        A.BANK.add = real_add
    ev1 = ((kept.get("entry") or {}).get("events") or [{}])[0]
    check("  a by-hand transition exclusion is banked beside the state one",
          (ev1.get("excluded") or {}).get("onset") == [99]
          and (ev1.get("excluded") or {}).get("pre") == [98],
          ev1.get("excluded"))

    # Nothing measured on transitions -> the flag says so.
    saved = A._ARC_CLIP.get(gid)
    A._ARC_CLIP[gid] = dict(saved, transition={"measured": False})
    A.BANK.add = fake_add
    try:
        client.post(base + "/bank", json={})
    finally:
        A.BANK.add = real_add
        A._ARC_CLIP[gid] = saved
    p2 = (kept.get("entry") or {}).get("parameters") or {}
    check("NEGATIVE CONTROL: with no transition reading, transition_measured "
          "is false and no length is claimed",
          p2.get("transition_measured") is False
          and p2.get("transition_before_s") is None, p2)

    # ---- coupling: refused on the real entry ----
    head("coupling, kind = transition, for %s" % sm.get("label"))
    real = A._coupling_entry(gid)
    rp = ((real or {}).get("source") or {}).get("parameters") or {}
    note("the real banked entry: transition_measured = %r"
         % rp.get("transition_measured"))
    cbase = "/api/arc/coupling/" + gid
    if not rp.get("transition_measured"):
        r = client.post(cbase + "/run", json={"pair_id": 1,
                                              "kind": "transition"})
        msg = (r.get_json() or {}).get("error", "")
        check("a transition run on an entry nobody checked is refused",
              r.status_code == 409 and "Spark" in msg, msg[:200])
        note("it says: " + msg)
        r = client.get(cbase + "/overview?kind=transition")
        o = r.get_json() or {}
        check("  and the overview says the same, with no wire grid",
              o.get("ok") and o.get("transition_measured") is False
              and o.get("refused") and not o.get("events"),
              str(o.get("refused"))[:160])
    r = client.get(cbase + "/overview")
    o = r.get_json() or {}
    check("the state overview is unchanged: four windows, pad_s, no "
          "transition lengths",
          o.get("windows") == ["pre", "cue1", "cue2", "post"]
          and any(p["id"] == "pad_s" for p in o.get("params") or [])
          and not any(p["id"] in ("before_s", "after_s")
                      for p in o.get("params") or []))

    # ---- coupling: end to end on the entry the bank would have written ----
    fake = copy.deepcopy(real)
    captured = kept.get("entry")
    # The entry the first bank call above captured, with the real id.
    A.BANK.add = fake_add
    try:
        client.post(base + "/bank", json={"excluded": {}})
    finally:
        A.BANK.add = real_add
    captured = kept["entry"]
    fake["events"] = captured["events"]
    fake.setdefault("source", {})["parameters"] = captured["parameters"]
    real_entry_fn = A._coupling_entry
    A._coupling_entry = lambda g: fake if g == gid else real_entry_fn(g)
    try:
        r = client.get(cbase + "/overview?kind=transition")
        o = r.get_json() or {}
        check("with transition clipping banked, the overview has three "
              "windows and the transition lengths",
              o.get("ok") and o.get("windows") == ["onset", "switch", "offset"]
              and o.get("transition_measured") is True
              and any(p["id"] == "before_s" and p["max"] == 1.0
                      for p in o.get("params") or [])
              and not any(p["id"] == "pad_s" for p in o.get("params") or []),
              str(o)[:200])
        check("  and a grid of 12 regions x 3 windows per pair",
              all(len(ev["regions"]) == 12
                  and all(len(r_["windows"]) == 3 for r_ in ev["regions"])
                  for ev in o.get("events") or []) and o.get("events"))

        r = client.post(cbase + "/run", json={
            "pair_id": 1, "kind": "transition",
            "params": {"before_s": 1.5}})
        msg = (r.get_json() or {}).get("error", "")
        check("a transition longer than the one measured is refused",
              r.status_code == 400 and "measured" in msg, msg[:200])

        # Pick the pair whose transition windows lost the most wires, so the
        # one-wire check has something to rescue.
        per_pair = {}
        for i, ev in enumerate(fake["events"], start=1):
            cl = ev.get("clipped") or {}
            per_pair[i] = sum(len(cl.get(w) or [])
                              for w in ("onset", "switch", "offset"))
        want_pair = max(per_pair, key=lambda k: (per_pair[k], -k))
        note("running pair %d (%d transition wire-windows lost)"
             % (want_pair, per_pair[want_pair]))
        t = time.time()
        r = client.post(cbase + "/run", json={"pair_id": want_pair,
                                              "kind": "transition"})
        out = r.get_json() or {}
        note("transition run: %.1f s" % (time.time() - t))
        check("the transition run answers",
              r.status_code == 200 and out.get("ok"),
              r.get_data(as_text=True)[:200])
        names = [w["window"] for w in out.get("windows") or []]
        check("  in three windows, onset, switch, offset",
              names == ["onset", "switch", "offset"], names)
        check("  each window's length is before + after",
              all(abs(w["duration_s"] - 3.0) < 1e-6
                  for w in out.get("windows") or []))
        prm_ = out.get("params") or {}
        check("  the run says what kind it is and at what lengths",
              prm_.get("kind") == "transition" and prm_.get("before_s") == 1.0
              and prm_.get("after_s") == 2.0, prm_)
        ev = fake["events"][want_pair - 1]
        drop = A._coupling_drop(ev, bad)
        present = {int(n) for n, _p in nlx.list_csc_files(
            got["path"], even_only=False)}
        cmap = coupling.dewey_map()
        rat, probe = A._coupling_probe(sm)
        blocked = A._coupling_blocked(probe)
        wrong, rescued, n_checked = [], 0, 0
        for w in out.get("windows") or []:
            ex = set((drop.get(w["window"]) if isinstance(drop, dict)
                      else drop) or [])
            for name, reg in w["regions"].items():
                if name in blocked:
                    if reg.get("channel") is not None:
                        wrong.append((w["window"], name, "histology"))
                    continue
                usable = [c for c in sorted(cmap[name])
                          if c not in ex and c not in set(bad)
                          and c in present]
                want_c = usable[0] if usable else None
                n_checked += 1
                if reg.get("channel") != want_c:
                    wrong.append((w["window"], name, reg.get("channel"),
                                  want_c))
                lowest = [c for c in sorted(cmap[name])
                          if c not in set(bad) and c in present]
                if want_c is not None and lowest and want_c != lowest[0]:
                    rescued += 1
        check("every region's one wire is the lowest-numbered one not "
              "excluded in that transition window",
              not wrong and n_checked > 0, wrong[:4])
        note("%d region-windows checked; %d rescued by a spare wire after "
             "the lowest clipped; %d regions ruled out by histology"
             % (n_checked, rescued, len(blocked)))
        sanity = out.get("sanity") or {}
        check("  and the matrix's sanity is built from those windows",
              all(set((rec.get("windows") or {}).keys())
                  == {"onset", "switch", "offset"}
                  for rec in sanity.get("channel_sanity") or []))

        # Negative control: the engine handed only the state exclusion.
        if per_pair[want_pair]:
            st_only = {k: v for k, v in drop.items()
                       if k in ("pre", "cue1", "cue2", "post")}
            wins = coupling.windows_of("transition")
            got_ = coupling._signals_for_windows(
                got["path"], cmap,
                spark.transition_windows(_pair(A, ev, want_pair), 1.0, 2.0),
                st_only, blocked=blocked)
            leaked = []
            for wname in wins:
                clipped = set((ev.get("clipped") or {}).get(wname) or [])
                for name, reg in got_[wname]["regions"].items():
                    if reg.get("channel") in clipped:
                        leaked.append((wname, name, reg["channel"]))
            check("NEGATIVE CONTROL: without the transition exclusion a "
                  "clipped wire is chosen", len(leaked) > 0,
                  "no region's chosen wire was clipped anyway")
            note("without it: %s" % leaked[:4])

        blob = A._coupling_csv(out, sm.get("label"), fake.get("id"))
        lines = blob.strip().splitlines()
        hdr = lines[0].split(",")
        check("the CSV names the transition windows and says the kind",
              "window_kind" in hdr and len(lines) > 1
              and all(",transition," in ln or ln.endswith(",transition,1.0,2.0")
                      for ln in lines[1:])
              and {ln.split(",")[4] for ln in lines[1:]}
              <= {"onset", "switch", "offset"}, lines[:2])
    finally:
        A._coupling_entry = real_entry_fn


def _pair(A, ev, n):
    return A._coupling_pair(ev, n)


def state_coupling_unchanged(A, gid, sm):
    """One pair, state kind, against the pre-change engine."""
    from backend import coupling
    head("state coupling unchanged (%s, pair 1)" % sm.get("label"))
    path = os.path.join(HERE, "_coupling_state_reference.py")
    if not os.path.exists(path):
        note("no reference copy of the pre-change coupling engine; skipped")
        return
    spec = importlib.util.spec_from_file_location("backend._coupling_ref",
                                                  path)
    ref = importlib.util.module_from_spec(spec)
    ref.__package__ = "backend"
    spec.loader.exec_module(ref)
    entry = A._coupling_entry(gid)
    ev = entry["events"][0]
    pair = A._coupling_pair(ev, 1)
    bad = sorted(int(c) for c in (sm.get("bad_channels") or []))
    drop = A._coupling_drop(ev, bad)
    rat, probe = A._coupling_probe(sm)
    blocked = A._coupling_blocked(probe)
    folder = (sm.get("here") or [None])[0]
    t = time.time()
    new = coupling.pair_connectivity(folder, pair, exclude_by_channel=drop,
                                     blocked_regions=blocked)
    note("state run: %.1f s" % (time.time() - t))
    old_drop = ref.excluded_for(ev)
    if isinstance(old_drop, dict):
        old_drop = {w: sorted(set(v) | set(bad)) for w, v in old_drop.items()}
        for w in ref.CLIP_WINDOW_NAMES:
            old_drop.setdefault(w, list(bad))
    old = ref.pair_connectivity(folder, pair, exclude_by_channel=old_drop,
                                blocked_regions=blocked)
    a = json.loads(json.dumps(new["windows"], sort_keys=True, default=str))
    b = json.loads(json.dumps(old["windows"], sort_keys=True, default=str))
    check("a state run's windows are identical to the pre-change engine's",
          a == b)
    pa = dict(new["params"])
    extra = {k: pa.pop(k) for k in ("kind", "before_s", "after_s") if k in pa}
    check("  and its params too, plus only the new `kind`",
          pa == old["params"] and extra == {"kind": "state"}, extra)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
