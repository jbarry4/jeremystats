"""
Downsample Neuralynx .ncs files to 1000 Hz and write valid .ncs output files.

Output: <input_dir>/downsampled_1kHz/  containing one .ncs per channel

Dependencies: numpy, scipy
"""

import re
import struct
import numpy as np
from pathlib import Path
from scipy.signal import resample_poly
from math import gcd


# ── Neuralynx .ncs binary layout ──────────────────────────────────────────────
NCS_HEADER_BYTES       = 16384
NCS_RECORD_BYTES       = 1044
NCS_SAMPLES_PER_RECORD = 512
NCS_RECORD_FMT    = "<QIIi" + "h" * NCS_SAMPLES_PER_RECORD
NCS_RECORD_STRUCT = struct.Struct(NCS_RECORD_FMT)


def read_ncs(path: Path):
    """Return (header_bytes, channel_num, timestamps_us, samples_int16, fs_hz)."""
    data = path.read_bytes()
    header_raw = data[:NCS_HEADER_BYTES]
    body = data[NCS_HEADER_BYTES:]
    n_records = len(body) // NCS_RECORD_BYTES

    timestamps  = np.empty(n_records, dtype=np.uint64)
    samples     = np.empty(n_records * NCS_SAMPLES_PER_RECORD, dtype=np.int16)
    fs_hz       = None
    channel_num = 0

    for i in range(n_records):
        rec = NCS_RECORD_STRUCT.unpack_from(body, i * NCS_RECORD_BYTES)
        timestamps[i] = rec[0]
        channel_num   = rec[1]
        if fs_hz is None:
            fs_hz = int(rec[2])
        samples[i * NCS_SAMPLES_PER_RECORD : (i + 1) * NCS_SAMPLES_PER_RECORD] = rec[4:]

    return header_raw, channel_num, timestamps, samples, fs_hz


def patch_header(header_raw: bytes, new_fs: int) -> bytes:
    """Update -SamplingFrequency in the ASCII header and return padded bytes."""
    text = header_raw.rstrip(b"\x00").decode("latin-1", errors="replace")
    text = re.sub(r"(-SamplingFrequency\s+)\d+", rf"\g<1>{new_fs}", text)
    encoded = text.encode("latin-1", errors="replace")
    return encoded.ljust(NCS_HEADER_BYTES, b"\x00")[:NCS_HEADER_BYTES]


def downsample(signal: np.ndarray, fs_in: int, fs_out: int) -> np.ndarray:
    """Anti-aliased rational resampling; returns float32."""
    factor = gcd(fs_in, fs_out)
    return resample_poly(signal.astype(np.float32), fs_out // factor, fs_in // factor)


def write_ncs(path: Path, header: bytes, channel_num: int,
              samples: np.ndarray, ts0_us: int, fs_out: int):
    """Pack samples into 512-sample NCS records and write to path."""
    samples_i16 = np.clip(np.round(samples), -32768, 32767).astype(np.int16)

    n_full    = len(samples_i16) // NCS_SAMPLES_PER_RECORD
    remainder = len(samples_i16) %  NCS_SAMPLES_PER_RECORD
    n_records = n_full + (1 if remainder else 0)

    # microseconds between records at the new sample rate
    us_per_record = int(round(NCS_SAMPLES_PER_RECORD / fs_out * 1e6))

    with open(path, "wb") as f:
        f.write(header)
        for i in range(n_records):
            start  = i * NCS_SAMPLES_PER_RECORD
            chunk  = samples_i16[start : start + NCS_SAMPLES_PER_RECORD]
            nvalid = len(chunk)
            # pad last record with zeros if needed
            if nvalid < NCS_SAMPLES_PER_RECORD:
                chunk = np.pad(chunk, (0, NCS_SAMPLES_PER_RECORD - nvalid))
            ts = ts0_us + i * us_per_record
            f.write(NCS_RECORD_STRUCT.pack(ts, channel_num, fs_out, nvalid, *chunk))


def process_directory(input_dir: str, target_fs: int = 1000):
    input_path  = Path(input_dir)
    output_path = input_path / "downsampled_1kHz"
    output_path.mkdir(exist_ok=True)

    ncs_files = sorted(input_path.glob("CSC*.ncs"),
                       key=lambda p: int("".join(filter(str.isdigit, p.stem)) or 0))

    if not ncs_files:
        print("No CSC*.ncs files found.")
        return

    print(f"Found {len(ncs_files)} channels.  Target: {target_fs} Hz")
    print(f"Output → {output_path}\n")

    for ncs in ncs_files:
        print(f"  {ncs.name} ...", end=" ", flush=True)
        header_raw, ch_num, ts_us, raw, fs = read_ncs(ncs)

        print(f"(fs={fs} Hz → {target_fs} Hz)", end=" ", flush=True)

        ds      = downsample(raw, fs, target_fs)
        header  = patch_header(header_raw, target_fs)
        out_ncs = output_path / ncs.name

        write_ncs(out_ncs, header, ch_num, ds, int(ts_us[0]), target_fs)
        print("done")

    print(f"\nDone.  {len(ncs_files)} .ncs files written to:\n  {output_path}")


if __name__ == "__main__":
    INPUT_DIR = r"D:\PTEN\CTL\M6_PtenMissCTL\M6s4sept13\2023-09-13_17-24-49"
    TARGET_HZ = 1000

    process_directory(INPUT_DIR, TARGET_HZ)
