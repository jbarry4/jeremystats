"""
Extract a random 5-second snippet from an LL_input .mat file.

The .mat was written by VACC_CSC2MAT_uV_disk (v7.3 / HDF5 format).
Key variables:
    d    — [nChannels x nSamples]  single/double, microvolts
    sfx  — scalar, sampling rate in Hz

Uses h5py to slice lazily — no need to load the full file into RAM.

Output: same folder, named  <stem>_snip_<start>s-<end>s.mat
                        and  <stem>_snip_<start>s-<end>s_info.txt

Dependencies: numpy, scipy, h5py
"""

import random
import datetime
import numpy as np
import h5py
import scipy.io
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
MAT_PATH = r"C:\Users\Z390\Downloads\Matfile\LL_input_2023-09-13_17-24-49_mex_disk_uV.mat"
SNIP_SEC = 5
# ─────────────────────────────────────────────────────────────────────────────


def write_info_txt(txt_path: Path, mat_path: Path, fs: float,
                   n_ch: int, n_samp: int, dtype: str,
                   start_samp: int, snip_len: int,
                   t_start: float, t_end: float, all_keys: list[str]):
    lines = [
        "=" * 60,
        "SNIPPET METADATA",
        "=" * 60,
        f"Generated     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "── Source file ──────────────────────────────────────────",
        f"  Path         : {mat_path}",
        f"  Size on disk : {mat_path.stat().st_size / 1e9:.3f} GB",
        f"  Format       : MATLAB v7.3 / HDF5",
        "",
        "── Full recording ───────────────────────────────────────",
        f"  Channels     : {n_ch}",
        f"  Samples      : {n_samp}",
        f"  Duration     : {n_samp / fs:.2f} s",
        f"  Sampling rate: {fs} Hz",
        f"  Data dtype   : {dtype}",
        f"  Units        : microvolts",
        "",
        "── .mat variable inventory ──────────────────────────────",
    ]
    for k in all_keys:
        lines.append(f"  {k}")
    lines += [
        "",
        "── Snippet ──────────────────────────────────────────────",
        f"  Start sample : {start_samp}",
        f"  Length       : {snip_len} samples  ({snip_len / fs:.3f} s)",
        f"  t_start      : {t_start:.6f} s",
        f"  t_end        : {t_end:.6f} s",
        "",
        "── Output variable layout ───────────────────────────────",
        f"  d            : [{n_ch} x {snip_len}]  (channels × samples)",
        f"  sfx          : {fs}",
        f"  t_start      : {t_start:.6f}",
        f"  t_end        : {t_end:.6f}",
        f"  units        : 'microvolts'",
        "=" * 60,
    ]
    txt_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    mat_path = Path(MAT_PATH)

    with h5py.File(mat_path, "r") as f:
        all_keys = list(f.keys())

        fs     = float(np.array(f["sfx"]).flat[0])
        print(f"Sampling rate (sfx): {fs} Hz")

        dset   = f["d"]
        n_samp = dset.shape[0]
        n_ch   = dset.shape[1]
        dtype  = str(dset.dtype)
        print(f"Data shape (HDF5 view): {dset.shape}  → {n_ch} channels × {n_samp} samples")
        print(f"Recording length: {n_samp / fs:.1f} s")

        snip_len  = int(SNIP_SEC * fs)
        max_start = n_samp - snip_len
        if max_start <= 0:
            raise ValueError(f"Recording shorter than {SNIP_SEC}s at {fs} Hz.")

        start   = random.randint(0, max_start)
        t_start = start / fs
        t_end   = t_start + SNIP_SEC
        print(f"\nRandom snippet: {t_start:.2f}s – {t_end:.2f}s  ({snip_len} samples)")

        snip = dset[start : start + snip_len, :].T   # [nChannels x snip_len]

    stem     = f"{mat_path.stem}_snip_{int(t_start)}s-{int(t_end)}s"
    out_mat  = mat_path.parent / f"{stem}.mat"
    out_txt  = mat_path.parent / f"{stem}_info.txt"

    scipy.io.savemat(str(out_mat), {
        "d":       snip,
        "sfx":     np.float64(fs),
        "t_start": np.float64(t_start),
        "t_end":   np.float64(t_end),
        "units":   "microvolts",
    })
    print(f"Saved .mat → {out_mat}")

    write_info_txt(out_txt, mat_path, fs, n_ch, n_samp, dtype,
                   start, snip_len, t_start, t_end, all_keys)
    print(f"Saved .txt → {out_txt}")


if __name__ == "__main__":
    main()
