# -*- coding: utf-8 -*-
"""A stacked time-frequency panel draws each channel in the row it labels.
Offline.

    python tools/check_tf_stack_order.py

The fault this guards (2026-10-13): `_panel_tf` stacked one spectrogram per
channel in channel order and then flipped the whole image so each block's
low frequency sat at its bottom. The flip also reversed the order of the
blocks, while the client -- and the figure builder -- label rows top-down
from `rows`. Every row carried the label of its mirror image: a discharge on
CSC57 read as CSC1, on a probe where the order of the rows is the point.

Four synthetic channels, ONE of them with a strong tone, through the real
renderer for each transform it has (legacy STFT, high-resolution STFT,
Morlet CWT), with the loud one in each position in turn. The image is
decoded and the hot quarter must be the quarter labelled with the loud
channel's name. And within a block, the tone must sit at its frequency's
height: low frequency at the bottom of the block, as MATLAB draws it.
"""
import base64
import io
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import analysis as A  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-72s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


FS = 2000.0
N = int(FS)
T = np.arange(N) / FS
CHANS = [{"index": i, "number": num, "label": "CSC%d" % num}
         for i, num in enumerate([1, 9, 17, 25])]


def render(loud, method, hires, tone_hz):
    rng = np.random.default_rng(7)
    rows = [rng.normal(0, 1, N) for _ in CHANS]
    rows[loud] = rows[loud] + 60 * np.sin(2 * np.pi * tone_hz * T)
    real = {k: getattr(A, k) for k in
            ("_stack", "_fill_gaps", "_tf_channels", "_tf_pad_seconds")}
    A._stack = lambda session, spec, channels=None: (np.asarray(rows), CHANS,
                                                     0.0, FS)
    A._fill_gaps = lambda row, ch: row
    A._tf_channels = lambda spec, session: [c["index"] for c in CHANS]
    A._tf_pad_seconds = lambda *a, **k: 0.0
    try:
        spec = {"t0": 0.0, "t1": 1.0, "fmin": 20, "fmax": 900,
                "tf_mode": "stack", "tf_channels": [0, 1, 2, 3],
                "cmap": "gray"}
        if method == "stft":
            spec["stft_mode"] = "hires" if hires else "legacy"
        out = A._panel_tf({"duration_s": 1.0, "fs": FS}, spec, method)
    finally:
        for k, v in real.items():
            setattr(A, k, v)
    import matplotlib.image as mpimg
    png = base64.b64decode(out["image"].split(",", 1)[1])
    lum = mpimg.imread(io.BytesIO(png))[..., :3].mean(axis=2)
    return out, lum


def main():
    for method, hires, name in (("stft", False, "legacy STFT"),
                                ("stft", True, "high-resolution STFT"),
                                ("cwt", False, "Morlet CWT")):
        print("\n" + name)
        for loud in range(len(CHANS)):
            out, lum = render(loud, method, hires, 300.0)
            labels = [r["label"] for r in out["rows"]]
            q = lum.shape[0] // len(labels)
            heat = [float(lum[i * q:(i + 1) * q].mean())
                    for i in range(len(labels))]
            hot = int(np.argmax(heat))
            check("%s alone is drawn in the row labelled %s"
                  % (CHANS[loud]["label"], CHANS[loud]["label"]),
                  labels[hot] == CHANS[loud]["label"],
                  "hot row %d is labelled %s; rows %s; heat %s"
                  % (hot, labels[hot], labels, [round(h, 3) for h in heat]))
        # Inside a block: a low tone sits lower than a high one.
        _, lo = render(0, method, hires, 60.0)
        _, hi = render(0, method, hires, 700.0)
        q = lo.shape[0] // len(CHANS)
        y_lo = int(np.argmax(lo[:q].mean(axis=1)))
        y_hi = int(np.argmax(hi[:q].mean(axis=1)))
        check("within a block, 60 Hz is drawn below 700 Hz",
              y_lo > y_hi, "60 Hz at row %d, 700 Hz at row %d (0 = top)"
              % (y_lo, y_hi))
    print("\n" + ("ALL PASS" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
