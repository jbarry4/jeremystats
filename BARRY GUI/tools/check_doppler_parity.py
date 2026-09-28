# -*- coding: utf-8 -*-
"""check_doppler_parity.py -- prove the port is the MATLAB.

`backend/doppler.py` is a Python transcription of Jon Kleen's
`LLspikedetector.m`. A transcription that is nearly right is worse than one
that is obviously wrong, because every event moves a little and nothing looks
broken. So this runs the real MATLAB and asserts exact equality.

WHAT IS CHECKED, IN ORDER

  1. `matlab_prctile` against MATLAB's own `prctile` on random vectors.
     MATLAB places the k-th of n sorted values at (k-0.5)/n; numpy's default
     places it at k/(n-1), and on a billion line-length samples those land on
     different numbers.

  2. `linelength` (a cumulative sum, O(n)) against the literal sliding loop
     in the .m file (O(n*w)). Same arithmetic is exactly the kind of claim
     that wants a test.

  3. `llspikedetector` against `LLspikedetector.m`: `ets` and `ech` equal
     element for element, on a synthetic matrix with planted discharges and,
     with --session, on a real slice of a recording.

  4. `_events_from_mask` -- the shared post-transform half that the streaming
     run uses -- against the literal port, so the two cannot drift apart.

A failure prints the first differing row rather than a boolean, because
"they differ" is not a thing anybody can act on.

    python tools/check_doppler_parity.py
    python tools/check_doppler_parity.py --session "D:/KCNT1/.../2022-03-18_15-38-40"
    python tools/check_doppler_parity.py --keep     # leave the workspace to look at
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
REPO = os.path.dirname(APP)
sys.path.insert(0, APP)

from backend import doppler                              # noqa: E402
from backend import sysinfo                              # noqa: E402

# Where the lab keeps the original. Both spellings, because the tree has the
# detector in two places and only one of them is the one on the path.
MFILE_DIRS = [
    os.path.join(REPO, "IED", "03_IED_Detection"),
    os.path.join(REPO, "IED"),
    os.path.join(REPO, "VACC Code", "KCNT1 Urethane"),
]

FAILS = []


def say(line, bad=False):
    print(("  FAIL  " if bad else "  ok    ") + line)


def check(what, ok, note=""):
    if not ok:
        FAILS.append(what)
    say(what + (("   [" + note + "]") if note else ""), not ok)
    return ok


def head(title):
    print("")
    print("=== " + title + " ===")


def find_mfile():
    for d in MFILE_DIRS:
        p = os.path.join(d, "LLspikedetector.m")
        if os.path.isfile(p):
            return d
    return None


def run_matlab(exe, work, body):
    """Run one MATLAB statement in `work`, return (ok, output)."""
    safe = work.replace("'", "''")
    mdir = find_mfile().replace("'", "''")
    setup = ("addpath('" + mdir + "'); cd('" + safe + "'); ")
    cmd = [exe, "-batch", setup + body]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except Exception as e:                                # noqa: BLE001
        return False, str(e)
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode == 0, out


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def synthetic(n_ch=12, seconds=120.0, fs=1000.0, seed=7, n_events=140):
    """Channels of pink-ish noise with discharges planted in some of them.

    Planted rather than random so that a detector that finds nothing, or
    everything, is visibly wrong before any comparison happens. The events
    deliberately vary in how many channels they involve, because `ech` is
    half of what is being checked.
    """
    rng = np.random.default_rng(seed)
    n = int(seconds * fs)
    x = rng.standard_normal((n_ch, n)) * 12.0
    # Slow drift, so the line-length transform has something to ignore.
    t = np.arange(n) / fs
    x += 40.0 * np.sin(2 * np.pi * 2.0 * t)[None, :]
    # Mains, so a filtered run has something to remove.
    x += 8.0 * np.sin(2 * np.pi * 60.0 * t)[None, :]

    at = np.linspace(1.0, seconds - 1.0, n_events)
    for k, when in enumerate(at):
        i = int(when * fs)
        wide = 2 + (k % (n_ch - 1))
        rows = rng.choice(n_ch, size=wide, replace=False)
        w = int(0.03 * fs)
        spike = np.hanning(w * 2) * (250.0 + 40.0 * (k % 5))
        spike[w:] *= -0.6
        for r in rows:
            x[r, i:i + spike.size] += spike[:max(0, n - i)]
    return x, fs


def real_slice(path, seconds=60.0, max_ch=8):
    """A real recording, concatenated, the way the detector would read it."""
    from backend import continuity, csc
    sess = csc.open_session(path, even_only=True, invert=True)
    rep = continuity.check(path)
    if not rep or not rep.get("ok"):
        raise SystemExit("That recording has no usable segmentation.")
    fs = float(rep.get("fs") or sess.get("fs") or 30000.0)
    chans = (sess.get("channels") or [])[:max_ch]
    rows = []
    for c in chans:
        raw, _t0, _fs = csc._read_channel_window(sess, c, 0.0, seconds)
        rows.append(np.asarray(raw, dtype=np.float64))
    n = min(r.size for r in rows)
    return np.stack([r[:n] for r in rows]), fs


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------

def check_prctile(exe, work):
    head("prctile -- MATLAB places the k-th of n at (k-0.5)/n")
    rng = np.random.default_rng(3)
    vecs = [rng.standard_normal(1),
            rng.standard_normal(2),
            rng.standard_normal(17),
            rng.standard_normal(1000) * 50,
            rng.exponential(3.0, 9999)]
    ps = [50.0, 90.0, 99.0, 99.9, 0.1]
    from scipy.io import loadmat, savemat
    savemat(os.path.join(work, "pin.mat"),
            {"v%d" % i: v.reshape(1, -1) for i, v in enumerate(vecs)})
    body = ("S=load('pin.mat'); ps=[" + " ".join("%r" % p for p in ps) + "]; "
            "out=zeros(" + str(len(vecs)) + ",numel(ps)); "
            "for i=1:" + str(len(vecs)) + "; "
            "v=S.(sprintf('v%d',i-1)); "
            "for j=1:numel(ps); out(i,j)=prctile(v,ps(j)); end; end; "
            "save('pout.mat','out');")
    ok, out = run_matlab(exe, work, body)
    if not check("MATLAB computed prctile", ok, out.strip()[-200:]):
        return
    got = loadmat(os.path.join(work, "pout.mat"))["out"]
    worst, where = 0.0, ""
    for i, v in enumerate(vecs):
        for j, p in enumerate(ps):
            mine = doppler.matlab_prctile(v, p)
            theirs = float(got[i, j])
            # RELATIVE, not absolute. The two implementations do the
            # same interpolation in a different order, so they differ in
            # the last bit or two of a float64 -- 1.6e-12 on a value of
            # 152. A convention mismatch, which is what this check is for,
            # is not subtle: it lands on a different order statistic
            # entirely and shows up as whole percent.
            d = abs(mine - theirs) / max(1.0, abs(theirs))
            if d > worst:
                worst, where = d, "n=%d p=%g  %.17g vs %.17g" % (
                    v.size, p, mine, theirs)
    check("every prctile matches to 1e-12 relative", worst < 1e-12,
          where or "max relative diff %.3g" % worst)


def check_linelength():
    head("linelength -- the cumulative sum is the sliding loop")
    rng = np.random.default_rng(11)
    for n_ch, n, w in ((1, 200, 13), (5, 733, 40), (3, 64, 64)):
        d = rng.standard_normal((n_ch, n)) * 100
        fast = doppler.linelength(d, w)
        slow = np.full((n_ch, n), np.nan)
        for i in range(n - w):                            # MATLAB 1..N-w
            slow[:, i] = np.sum(np.abs(np.diff(d[:, i:i + w], axis=1)),
                                axis=1)
        a, b = np.nan_to_num(fast, nan=-1), np.nan_to_num(slow, nan=-1)
        bad = np.flatnonzero(np.abs(a - b) > 1e-9)
        check("n_ch=%d n=%d w=%d" % (n_ch, n, w), bad.size == 0,
              "" if bad.size == 0 else
              "first differs at %d: %.17g vs %.17g"
              % (bad[0], a.ravel()[bad[0]], b.ravel()[bad[0]]))
        # The NaN tail has to be in the same place, not merely absent.
        check("n_ch=%d w=%d  NaN tail starts at N-w" % (n_ch, w),
              bool(np.all(np.isnan(fast[:, n - w:])))
              and bool(np.all(np.isfinite(fast[:, :n - w]))))


def check_detector(exe, work, d, fs, label, llw=0.04, prc=99.9, badch=None,
                   as_single=False):
    """`as_single` hands MATLAB a `single` matrix, which is what the lab's
    own `vacc_ied_detect1.m` does (`d = nan(..., 'single')`, line 240), so
    MATLAB's `sum` inside the transform runs in single precision. The port
    always transforms in float64."""
    head("LLspikedetector -- " + label)
    from scipy.io import loadmat, savemat
    if badch is None:
        badch = np.zeros(d.shape[0], dtype=bool)
    savemat(os.path.join(work, "din.mat"),
            {"d": d.astype(np.float32) if as_single else d,
             "sfx": float(fs), "llw": float(llw), "prc": float(prc),
             "badch": badch.astype(float).reshape(1, -1)},
            do_compression=False)
    body = ("S=load('din.mat'); "
            "[ets,ech]=LLspikedetector(S.d,S.sfx,S.llw,S.prc,logical(S.badch)); "
            "save('dout.mat','ets','ech','-v7');")
    ok, out = run_matlab(exe, work, body)
    if not check("MATLAB ran the detector", ok, out.strip()[-300:]):
        return None
    got = loadmat(os.path.join(work, "dout.mat"))
    m_ets = np.atleast_2d(got["ets"]).astype(np.int64)
    m_ech = np.atleast_2d(got["ech"]).astype(bool)
    if m_ets.size == 0:
        m_ets = m_ets.reshape(0, 2)

    p_ets, p_ech = doppler.llspikedetector(d, fs, llw, prc, badch)

    check("%s: found some events at all" % label, m_ets.shape[0] > 0,
          "MATLAB found %d" % m_ets.shape[0])
    if not check("%s: same number of events" % label,
                 p_ets.shape[0] == m_ets.shape[0],
                 "python %d, matlab %d" % (p_ets.shape[0], m_ets.shape[0])):
        return (p_ets, p_ech)

    same = np.flatnonzero(np.any(p_ets != m_ets, axis=1))
    check("%s: every [on off] identical" % label, same.size == 0,
          "" if same.size == 0 else
          "row %d: python %s, matlab %s"
          % (same[0], p_ets[same[0]].tolist(), m_ets[same[0]].tolist()))

    if p_ech.shape == m_ech.shape:
        rows = np.flatnonzero(np.any(p_ech != m_ech, axis=1))
        check("%s: every channel participation identical" % label,
              rows.size == 0,
              "" if rows.size == 0 else
              "row %d: python %s, matlab %s"
              % (rows[0], np.flatnonzero(p_ech[rows[0]]).tolist(),
                 np.flatnonzero(m_ech[rows[0]]).tolist()))
    else:
        check("%s: ech is the same shape" % label, False,
              "python %s, matlab %s" % (p_ech.shape, m_ech.shape))
    return (p_ets, p_ech)


def check_shared_half(d, fs, llw=0.04, prc=99.9):
    """The streaming run's post-transform half is the literal port's.

    `run()` cannot call `llspikedetector` -- it never holds every channel's
    transform at once -- so it calls `_events_from_mask` with a mask it built
    channel by channel. If those two ever disagree, a cluster run and a
    parity check are measuring different detectors.
    """
    head("_events_from_mask -- the streaming half equals the literal port")
    w = int(doppler.matlab_round(llw * fs))
    L = doppler.linelength(d, w)
    thr = doppler.matlab_prctile(L, prc)
    with np.errstate(invalid="ignore"):
        Li = L > thr
    # The streaming run cannot hold every value; it keeps each channel's
    # tail and takes the percentile from those. Exactly, or it is a
    # different threshold.
    for p in (prc, 99.0, 50.0, 10.0, 0.1):
        m = doppler.tail_size(p, L.size)
        tails = [doppler.keep_tail(r[np.isfinite(r)], p, m) for r in L]
        n_fin = int(np.isfinite(L).sum())
        a_thr = doppler.prctile_from_tail(np.concatenate(tails), n_fin, p, m)
        b_thr = doppler.matlab_prctile(L, p)
        check("prc %g: threshold from per-channel tails is the pooled one"
              % p, a_thr == b_thr, "%.17g vs %.17g" % (a_thr, b_thr))
    a_ets, a_ech = doppler._events_from_mask(Li, fs, llw)
    b_ets, b_ech = doppler.llspikedetector(d, fs, llw, prc, None)
    check("same number of events", a_ets.shape[0] == b_ets.shape[0],
          "streaming %d, literal %d" % (a_ets.shape[0], b_ets.shape[0]))
    if a_ets.shape == b_ets.shape:
        bad = np.flatnonzero(np.any(a_ets != b_ets, axis=1))
        check("every [on off] identical", bad.size == 0,
              "" if bad.size == 0 else "row %d" % bad[0])
        check("every participation identical",
              bool(np.array_equal(a_ech, b_ech)))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", help="a CSC folder to take a real slice from")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--single", action="store_true",
                    help="also hand MATLAB the real slice as single, the way "
                         "vacc_ied_detect1.m does")
    ap.add_argument("--keep", action="store_true",
                    help="leave the MATLAB workspace behind")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                    # noqa: BLE001
        pass

    exe = sysinfo.find_matlab()
    mdir = find_mfile()
    print("MATLAB   %s" % (exe or "-- not found"))
    print("Detector %s" % (os.path.join(mdir, "LLspikedetector.m")
                           if mdir else "-- not found"))
    if not mdir:
        print("\nLLspikedetector.m is not in this tree, so there is nothing "
              "to check against.")
        return 2

    # The two checks that need no MATLAB run first, so a machine without it
    # still gets an answer rather than nothing.
    check_linelength()
    d, fs = synthetic()
    check_shared_half(d, fs)

    if not exe:
        print("\nMATLAB was not found on this machine, so the comparison "
              "against it was skipped. The port's internal agreement was "
              "checked and is above.")
        print("")
        print("%d FAILED" % len(FAILS) if FAILS else "all passed")
        return 1 if FAILS else 0

    work = tempfile.mkdtemp(prefix="doppler_parity_")
    try:
        check_prctile(exe, work)
        check_detector(exe, work, d, fs, "synthetic, 12 channels")
        bad = np.zeros(d.shape[0], dtype=bool)
        bad[[1, 4]] = True
        check_detector(exe, work, d, fs, "synthetic, two channels bad",
                       badch=bad)
        check_detector(exe, work, d, fs, "synthetic, prc 99.0", prc=99.0)
        if args.session:
            try:
                rd, rfs = real_slice(args.session, args.seconds)
                name = "%.0f s of %s" % (
                    args.seconds, os.path.basename(args.session.rstrip("/\\")))
                check_detector(exe, work, rd, rfs, name)
                if args.single:
                    check_detector(exe, work, rd, rfs,
                                   name + ", MATLAB given single",
                                   as_single=True)
            except Exception as e:                        # noqa: BLE001
                check("read the real recording", False, str(e))
    finally:
        if args.keep:
            print("\nWorkspace left at %s" % work)
        else:
            shutil.rmtree(work, ignore_errors=True)

    print("")
    if FAILS:
        print("%d FAILED:" % len(FAILS))
        for f in FAILS:
            print("   " + f)
        return 1
    print("all passed -- the port is the MATLAB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
