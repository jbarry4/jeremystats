# -*- coding: utf-8 -*-
"""Step 2 -- read every recording once, and keep what the sweep needs.

Per recording, in DATA/<key>/:

  sig2k.npy        64 x N   every channel, inverted (lab convention), in uV,
                            anti-aliased and decimated 30 kHz -> 2 kHz.
                            The sweep and the waveform analysis run on this.
  ll30k_pool.npy   64 x B   the ORIGINAL detector's line length -- raw
                            30 kHz, 40 ms window, no filtering -- max-pooled
                            into 2 ms bins, so the old detector can be
                            reproduced as the baseline without re-reading.
  ll30k_hist.npy   64 x H   a fine histogram of that same 30 kHz line length
                            per channel (log10 bins, 0.001 decade wide), so the
                            original's percentile threshold over ANY channel set
                            is computed from the real full-rate distribution,
                            not from the pooled maxima.
  meta.json        channel numbers, lengths, rates

    python step2_cache.py              all recordings, 3 at a time
    python step2_cache.py m5_s7        just one
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy import signal as sig

import ied_common as C

LLW_ORIG = 0.040
HIST_LO, HIST_HI, HIST_N = 0.0, 7.0, 7000      # log10(LL) bins


def build(rec):
    from backend import nlx
    key = rec["key"]
    d = os.path.join(C.DATA, key)
    os.makedirs(d, exist_ok=True)
    meta_p = os.path.join(d, "meta.json")
    if os.path.exists(meta_p):
        return key, "cached"
    t0 = time.time()
    files = C.csc_files(rec["folder"])
    nums = sorted(files)
    # Lengths first, so every row has the same length (the shortest).
    n_raw = None
    w = int(round(LLW_ORIG * C.FS_RAW))
    sig_mm = pool_mm = hist = None
    for i, n in enumerate(nums):
        x, info = nlx.read_ncs(files[n], invert=True, to_microvolts=True)
        x = np.asarray(x, dtype=np.float32)
        if n_raw is None:
            n_raw = x.size
            n2 = n_raw // C.DEC
            nb = n_raw // (C.DEC * C.POOL)
            sig_mm = np.lib.format.open_memmap(
                os.path.join(d, "sig2k.tmp.npy"), mode="w+",
                dtype=np.float32, shape=(len(nums), n2))
            pool_mm = np.lib.format.open_memmap(
                os.path.join(d, "ll30k_pool.tmp.npy"), mode="w+",
                dtype=np.float32, shape=(len(nums), nb))
            hist = np.zeros((len(nums), HIST_N), dtype=np.int64)
        x = x[:n_raw]
        if x.size < n_raw:
            x = np.concatenate([x, np.full(n_raw - x.size, x[-1] if x.size
                                           else 0, np.float32)])
        # 2 kHz copy
        y = sig.resample_poly(x, 1, C.DEC).astype(np.float32)
        sig_mm[i, :] = y[:sig_mm.shape[1]]
        # the original's 30 kHz line length
        L = C.linelength(x[None, :], w)[0]
        ok = np.isfinite(L)
        lv = np.log10(np.maximum(L[ok], 1e-6))
        h, _e = np.histogram(lv, bins=HIST_N, range=(HIST_LO, HIST_HI))
        hist[i] = h
        k = C.DEC * C.POOL
        nbp = pool_mm.shape[1]
        Lp = L[:nbp * k].reshape(nbp, k)
        with np.errstate(invalid="ignore"):
            pool_mm[i, :] = np.nanmax(np.where(np.isnan(Lp), -np.inf, Lp),
                                      axis=1)
        del x, y, L, Lp, lv
    sig_mm.flush(); pool_mm.flush()
    del sig_mm, pool_mm
    os.replace(os.path.join(d, "sig2k.tmp.npy"), os.path.join(d, "sig2k.npy"))
    os.replace(os.path.join(d, "ll30k_pool.tmp.npy"),
               os.path.join(d, "ll30k_pool.npy"))
    np.save(os.path.join(d, "ll30k_hist.npy"), hist)
    with open(meta_p, "w") as fh:
        json.dump({"key": key, "channels": nums, "n_raw": int(n_raw),
                   "fs_raw": C.FS_RAW, "fs": C.FS, "dec": C.DEC,
                   "pool": C.POOL, "llw_orig": LLW_ORIG,
                   "hist": [HIST_LO, HIST_HI, HIST_N],
                   "seconds": n_raw / C.FS_RAW,
                   "built_s": round(time.time() - t0, 1)}, fh)
    return key, "built in %.0f s" % (time.time() - t0)


def main():
    gt = C.load_gt()
    want = set(sys.argv[1:])
    recs = [r for r in gt if not want or r["key"] in want]
    with ProcessPoolExecutor(max_workers=3) as ex:
        for key, msg in ex.map(build, recs):
            C.log(key, msg)


if __name__ == "__main__":
    main()
