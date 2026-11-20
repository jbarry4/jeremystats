"""
events.py -- Robust event/timestamp import with format autodetection.

The lab produces event marks from several tools, none of which agree:

  LLspikedetector   ets = [onset offset] in SAMPLES, ech = event x channel logical
  Toothy            DS_DF / SWR_DF CSV, one row per event, 'idx' is a SAMPLE index,
                    'ch' the detection channel, 'is_valid' a keep flag
  Spreadsheets      hand-curated .xlsx with whatever column names stuck

So this module does three things:

  1. INSPECT   open anything, report what columns/variables exist and a preview
  2. AUTODETECT  guess the format and the units (samples vs seconds vs ms)
  3. APPLY     turn it into a uniform event list, using an explicit mapping when
               the guess is wrong

The units question is the one that silently ruins a figure, so it is decided by
evidence rather than assumption: values are compared against the recording's
sample count and duration, and whichever interpretation lands inside the
recording wins. The verdict and its reasoning are reported back to the UI.
"""
from __future__ import annotations

import os
import numpy as np

# Column names seen in the wild, by role.
START_HINTS = ("start", "onset", "on", "idx", "index", "peak", "time", "times",
               "t", "ets", "sample", "samples", "timestamp", "begin", "pos")
END_HINTS = ("end", "offset", "off", "stop", "finish")
CHANNEL_HINTS = ("ch", "channel", "chan", "ech", "electrode", "chan_idx")
VALID_HINTS = ("is_valid", "valid", "keep", "status", "include")
LABEL_HINTS = ("label", "type", "class", "kind", "category", "name", "status")


class ImportError_(Exception):
    """Raised with a message meant to be shown to the user verbatim."""


# --------------------------------------------------------------------------
# Inspection
# --------------------------------------------------------------------------
def inspect(path, fs=None, n_samples=None, duration_s=None):
    """Open an event file and describe what is inside it, without committing."""
    if not os.path.exists(path):
        raise ImportError_("File not found: " + path)

    ext = os.path.splitext(path)[1].lower()
    if ext == ".mat":
        info = _inspect_mat(path)
    elif ext in (".csv", ".tsv", ".txt"):
        info = _inspect_table(path)
    elif ext in (".xlsx", ".xls"):
        info = _inspect_excel(path)
    elif ext == ".npy":
        info = _inspect_npy(path)
    else:
        raise ImportError_(
            "Unsupported event file type '%s'. Supported: .mat, .csv, .tsv, "
            ".txt, .xlsx, .xls, .npy" % (ext or "(none)"))

    info["path"] = path
    info["ext"] = ext
    info["suggestion"] = suggest_mapping(info, fs, n_samples, duration_s)
    return info


def _inspect_mat(path):
    """List the 2-D variables in a .mat, v7 and v7.3 alike."""
    variables = []
    try:
        import scipy.io as sio
        raw = sio.loadmat(path, squeeze_me=False, struct_as_record=False)
        for k, v in raw.items():
            if k.startswith("__"):
                continue
            arr = np.asarray(v)
            if arr.ndim > 2 or arr.size == 0:
                continue
            variables.append({
                "name": k, "shape": list(arr.shape),
                "dtype": str(arr.dtype),
                "preview": _preview(arr),
                "numeric": np.issubdtype(arr.dtype, np.number),
            })
        kind = "mat_v7"
    except NotImplementedError:
        import h5py
        with h5py.File(path, "r") as fh:
            for k in fh.keys():
                if k.startswith("#"):
                    continue
                obj = fh[k]
                if not hasattr(obj, "shape") or obj.ndim > 2:
                    continue
                arr = np.asarray(obj[()])
                variables.append({
                    "name": k, "shape": list(arr.shape),
                    "dtype": str(arr.dtype),
                    "preview": _preview(arr),
                    "numeric": np.issubdtype(arr.dtype, np.number),
                })
        kind = "mat_v73"
    except Exception as exc:
        raise ImportError_("Could not read '%s' as a MATLAB file: %s"
                           % (os.path.basename(path), exc))

    if not variables:
        raise ImportError_(
            "No usable arrays in %s. Expected something like 'ets' "
            "([onset offset] per row) or a plain list of times."
            % os.path.basename(path))
    return {"kind": kind, "variables": variables, "columns": None}


def _inspect_table(path):
    import csv as _csv
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
            sample = fh.read(64 * 1024)
            fh.seek(0)
            try:
                dialect = _csv.Sniffer().sniff(sample[:4096], delimiters=",\t;| ")
                delim = dialect.delimiter
            except Exception:
                delim = "\t" if path.lower().endswith(".tsv") else ","
            reader = _csv.reader(fh, delimiter=delim)
            rows = []
            for i, r in enumerate(reader):
                rows.append(r)
                if i >= 60:
                    break
    except OSError as exc:
        raise ImportError_("Could not open %s: %s" % (os.path.basename(path), exc))

    if not rows:
        raise ImportError_("%s is empty." % os.path.basename(path))

    header = rows[0]
    has_header = any(not _is_number(c) for c in header if str(c).strip() != "")
    if has_header:
        names = [str(c).strip() for c in header]
        body = rows[1:]
    else:
        names = ["col%d" % i for i in range(len(header))]
        body = rows

    columns = []
    for i, name in enumerate(names):
        vals = [r[i] for r in body[:40] if i < len(r)]
        columns.append({
            "name": name, "index": i,
            "preview": vals[:6],
            "numeric": bool(vals) and all(_is_number(v) or str(v).strip() == ""
                                          for v in vals),
        })
    return {"kind": "table", "delimiter": delim, "has_header": has_header,
            "columns": columns, "variables": None, "n_preview_rows": len(body),
            "column_names": names}


def _inspect_excel(path):
    try:
        import pandas as pd
    except ImportError:
        raise ImportError_(
            "Reading .xlsx needs pandas and openpyxl. Install them with:\n"
            "    pip install pandas openpyxl")
    try:
        xls = pd.ExcelFile(path)
        sheet = xls.sheet_names[0]
        df = xls.parse(sheet, nrows=60)
    except Exception as exc:
        raise ImportError_("Could not read %s: %s" % (os.path.basename(path), exc))

    columns = []
    for i, name in enumerate(df.columns):
        col = df[name]
        columns.append({
            "name": str(name), "index": i,
            "preview": [_jsonable(v) for v in col.head(6).tolist()],
            "numeric": bool(np.issubdtype(col.dtype, np.number)),
        })
    return {"kind": "excel", "sheet": sheet, "sheets": xls.sheet_names,
            "columns": columns, "variables": None}


def _inspect_npy(path):
    try:
        arr = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise ImportError_("Could not read %s: %s" % (os.path.basename(path), exc))
    return {"kind": "npy", "variables": [{
        "name": "array", "shape": list(arr.shape), "dtype": str(arr.dtype),
        "preview": _preview(arr), "numeric": np.issubdtype(arr.dtype, np.number),
    }], "columns": None}


# --------------------------------------------------------------------------
# Autodetection
# --------------------------------------------------------------------------
def suggest_mapping(info, fs=None, n_samples=None, duration_s=None):
    """Guess how to read this file. Returns a mapping the UI can edit."""
    kind = info["kind"]

    if kind.startswith("mat") or kind == "npy":
        names = {v["name"].lower(): v for v in info["variables"]}

        # LLspikedetector: ets is [nEvents x 2] in samples, ech is the
        # event x channel participation matrix.
        for cand in ("ets", "ets_all", "events"):
            if cand in names:
                v = names[cand]
                shape = v["shape"]
                two_col = (len(shape) == 2 and 2 in shape)
                ech = next((names[k] for k in ("ech", "ech_all") if k in names), None)
                return {
                    "format": "ets",
                    "variable": v["name"],
                    "start_col": 0, "end_col": 1 if two_col else None,
                    "channel_var": ech["name"] if ech else None,
                    "units": "samples",
                    "confidence": "high",
                    "why": "Found '%s'%s -- LLspikedetector output, "
                           "[onset offset] in samples."
                           % (v["name"], " with '%s'" % ech["name"] if ech else ""),
                }

        numeric = [v for v in info["variables"] if v["numeric"]]
        if numeric:
            v = max(numeric, key=lambda x: int(np.prod(x["shape"] or [0])))
            shape = v["shape"]
            two_col = len(shape) == 2 and 2 in shape and min(shape) == 2
            return {
                "format": "matrix", "variable": v["name"],
                "start_col": 0, "end_col": 1 if two_col else None,
                "channel_var": None,
                "units": _guess_units(v["preview"], fs, n_samples, duration_s),
                "confidence": "medium",
                "why": "Using the largest numeric array '%s' %s."
                       % (v["name"], shape),
            }
        raise_hint = ", ".join(v["name"] for v in info["variables"][:6])
        return {"format": None, "confidence": "none",
                "why": "No numeric array found. Variables present: " + raise_hint}

    # Tables ---------------------------------------------------------------
    cols = info["columns"] or []
    lower = {c["name"].lower().strip(): c for c in cols}
    names_l = list(lower.keys())

    # Toothy DS_DF / SWR_DF: 'idx' plus 'ch', usually with 'is_valid'.
    if "idx" in lower and any(h in lower for h in ("ch", "channel")):
        chan = "ch" if "ch" in lower else "channel"
        valid = next((h for h in VALID_HINTS if h in lower), None)
        return {
            "format": "toothy",
            "start_col": "idx", "end_col": None, "channel_col": chan,
            "valid_col": valid, "valid_value": 1,
            "label_col": "status" if "status" in lower else None,
            "units": "samples",
            "confidence": "high",
            "why": "Columns 'idx' and '%s'%s -- a Toothy detection table; "
                   "'idx' is a sample index." % (chan,
                   " with '%s'" % valid if valid else ""),
        }

    start = _first_hint(names_l, START_HINTS)
    end = _first_hint(names_l, END_HINTS)
    chan = _first_hint(names_l, CHANNEL_HINTS)
    label = _first_hint(names_l, LABEL_HINTS)

    if start is None:
        numeric_cols = [c["name"] for c in cols if c["numeric"]]
        if numeric_cols:
            start = numeric_cols[0]
    if start is None:
        return {"format": None, "confidence": "none",
                "why": "No numeric column that could hold event times. "
                       "Columns: " + ", ".join(c["name"] for c in cols[:8])}

    preview = lower.get(start.lower(), {}).get("preview", [])
    return {
        "format": "table",
        "has_header": info.get("has_header", True),
        "delimiter": info.get("delimiter", ","),
        "sheet": info.get("sheet"),
        "start_col": lower[start.lower()]["name"],
        "end_col": lower[end.lower()]["name"] if end else None,
        "channel_col": lower[chan.lower()]["name"] if chan else None,
        "label_col": lower[label.lower()]["name"] if label else None,
        "valid_col": None,
        "units": _guess_units(preview, fs, n_samples, duration_s),
        "confidence": "medium" if end or chan else "low",
        "why": "Matched column '%s' as the event time%s."
               % (start, " and '%s' as the end" % end if end else ""),
    }


def _first_hint(names, hints):
    for h in hints:
        if h in names:
            return h
    for h in hints:
        for n in names:
            if n.startswith(h) or h in n:
                return n
    return None


def _guess_units(preview, fs, n_samples, duration_s):
    """Decide samples / seconds / milliseconds from the actual magnitudes.

    Getting this wrong shifts every mark, so it is settled by asking which
    reading lands inside the recording rather than by convention.
    """
    vals = []
    for v in (preview or []):
        try:
            f = float(v)
            if np.isfinite(f):
                vals.append(abs(f))
        except (TypeError, ValueError):
            continue
    if not vals:
        return "samples"
    hi = max(vals)

    if duration_s and duration_s > 0:
        if hi <= duration_s * 1.05:
            return "seconds"
        if hi <= duration_s * 1000 * 1.05 and (not n_samples or hi > n_samples * 1.05):
            return "ms"
    fractional = any(abs(v - round(v)) > 1e-9 for v in vals)
    if fractional:
        # Sample indices are integers by construction, so a fractional value
        # means a real time unit -- pick the one that fits the recording.
        if duration_s and duration_s > 0:
            if hi <= duration_s * 1.05:
                return "seconds"
            if hi <= duration_s * 1000 * 1.05:
                return "ms"
        return "seconds"

    if n_samples and hi <= n_samples * 1.05:
        return "samples"
    # No recording context: a very large integer is almost certainly a sample
    # index, a small float almost certainly seconds.
    if hi > 100000:
        return "samples"
    if hi < 10000 and any(v != int(v) for v in vals):
        return "seconds"
    return "samples"


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------
def apply_mapping(path, mapping, fs, n_samples=None, duration_s=None):
    """Turn a file plus a mapping into a uniform event list.

    Returns events as dicts with `start`/`end` in SECONDS, plus optional
    channel and label, so everything downstream speaks one language.
    """
    if not mapping or not mapping.get("format"):
        raise ImportError_("No import mapping chosen.")
    if not fs or fs <= 0:
        raise ImportError_("Sampling rate is unknown, so sample indices cannot "
                           "be converted to time. Open a session first.")

    fmt = mapping["format"]
    ext = os.path.splitext(path)[1].lower()

    if fmt in ("ets", "matrix") or ext in (".mat", ".npy"):
        starts, ends, chans, labels = _apply_array(path, mapping)
    else:
        starts, ends, chans, labels = _apply_table(path, mapping)

    units = mapping.get("units", "samples")
    starts = _to_seconds(starts, units, fs)
    ends = _to_seconds(ends, units, fs) if ends is not None else None

    events = []
    for i, s in enumerate(starts):
        if not np.isfinite(s):
            continue
        ev = {"start": float(s)}
        if ends is not None and i < len(ends) and np.isfinite(ends[i]):
            ev["end"] = float(ends[i])
        if chans is not None and i < len(chans):
            try:
                ev["channel"] = int(chans[i])
            except (TypeError, ValueError):
                pass
        if labels is not None and i < len(labels):
            ev["label"] = str(labels[i])
        events.append(ev)

    events.sort(key=lambda e: e["start"])

    warnings = []
    if duration_s and events:
        out = sum(1 for e in events if e["start"] > duration_s * 1.001)
        if out:
            warnings.append(
                "%d of %d events fall past the end of the recording (%.1f s). "
                "The units are probably wrong -- try switching between "
                "samples/seconds/ms." % (out, len(events), duration_s))
        if events[0]["start"] < 0:
            warnings.append("Some events have negative times.")

    return {
        "ok": True,
        "events": events,
        "n": len(events),
        "units_used": units,
        "span": [events[0]["start"], events[-1]["start"]] if events else None,
        "warnings": warnings,
    }


def _apply_array(path, mapping):
    ext = os.path.splitext(path)[1].lower()
    var = mapping.get("variable")

    if ext == ".npy":
        arr = np.load(path, allow_pickle=False)
        extra = {}
    else:
        arr, extra = _load_mat_var(path, var, mapping.get("channel_var"))

    arr = np.asarray(arr, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    # MATLAB may hand back [2 x nEvents]; events should be the long axis.
    if arr.ndim == 2 and arr.shape[0] < arr.shape[1] and arr.shape[0] <= 4:
        arr = arr.T

    sc = mapping.get("start_col")
    sc = 0 if sc is None else int(sc)
    ec = mapping.get("end_col")
    if sc >= arr.shape[1]:
        raise ImportError_("Column %d does not exist in '%s' (it has %d column(s))."
                           % (sc, var, arr.shape[1]))
    starts = arr[:, sc]
    ends = arr[:, int(ec)] if ec is not None and int(ec) < arr.shape[1] else None

    chans = None
    ech = extra.get("channel")
    if ech is not None:
        ech = np.asarray(ech)
        if ech.ndim == 2:
            if ech.shape[0] != len(starts) and ech.shape[1] == len(starts):
                ech = ech.T
            if ech.shape[0] == len(starts):
                # ech is a logical event x channel matrix: report the first
                # participating channel as the representative one.
                with np.errstate(invalid="ignore"):
                    chans = np.argmax(ech > 0, axis=1) + 1
    return starts, ends, chans, None


def _load_mat_var(path, var, channel_var=None):
    extra = {}
    try:
        import scipy.io as sio
        raw = sio.loadmat(path, squeeze_me=False, struct_as_record=False)
        if var not in raw:
            avail = [k for k in raw if not k.startswith("__")]
            raise ImportError_("Variable '%s' is not in %s. Available: %s"
                               % (var, os.path.basename(path), ", ".join(avail)))
        arr = raw[var]
        if channel_var and channel_var in raw:
            extra["channel"] = raw[channel_var]
        return arr, extra
    except NotImplementedError:
        pass
    except ImportError_:
        raise
    except Exception as exc:
        raise ImportError_("Could not read %s: %s" % (os.path.basename(path), exc))

    import h5py
    with h5py.File(path, "r") as fh:
        if var not in fh:
            raise ImportError_("Variable '%s' is not in %s. Available: %s"
                               % (var, os.path.basename(path),
                                  ", ".join(k for k in fh.keys() if not k.startswith("#"))))
        arr = np.asarray(fh[var][()])
        if channel_var and channel_var in fh:
            extra["channel"] = np.asarray(fh[channel_var][()])
    return arr, extra


def _apply_table(path, mapping):
    ext = os.path.splitext(path)[1].lower()
    try:
        import pandas as pd
    except ImportError:
        raise ImportError_("Reading tables needs pandas. Install it with:\n"
                           "    pip install pandas")
    try:
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(path, sheet_name=mapping.get("sheet") or 0)
        elif mapping.get("has_header") is False:
            # No header row: read positionally and apply the same synthetic
            # col0..colN names the inspector displayed.
            df = pd.read_csv(path, sep=mapping.get("delimiter", ","),
                             engine="python", header=None)
            df.columns = ["col%d" % i for i in range(df.shape[1])]
        else:
            df = pd.read_csv(path, sep=mapping.get("delimiter", ","),
                             engine="python")
    except Exception as exc:
        raise ImportError_("Could not read %s: %s" % (os.path.basename(path), exc))

    df.columns = [str(c).strip() for c in df.columns]

    valid_col = mapping.get("valid_col")
    if valid_col and valid_col in df.columns:
        want = mapping.get("valid_value", 1)
        col = pd.to_numeric(df[valid_col], errors="coerce")
        if col.notna().any():
            df = df[col == float(want)]
        else:
            df = df[df[valid_col].astype(str).str.lower()
                    == str(want).lower()]

    def col_of(key):
        name = mapping.get(key)
        if not name:
            return None
        if name not in df.columns:
            raise ImportError_("Column '%s' is not in %s. Columns: %s"
                               % (name, os.path.basename(path),
                                  ", ".join(df.columns[:12])))
        return df[name]

    starts = pd.to_numeric(col_of("start_col"), errors="coerce").to_numpy()
    end_series = col_of("end_col")
    ends = pd.to_numeric(end_series, errors="coerce").to_numpy() if end_series is not None else None
    chan_series = col_of("channel_col")
    chans = pd.to_numeric(chan_series, errors="coerce").to_numpy() if chan_series is not None else None
    label_series = col_of("label_col")
    labels = label_series.astype(str).to_numpy() if label_series is not None else None
    return starts, ends, chans, labels


def _to_seconds(values, units, fs):
    if values is None:
        return None
    arr = np.asarray(values, dtype=float)
    if units == "samples":
        return arr / float(fs)
    if units == "ms":
        return arr / 1000.0
    if units == "us":
        return arr / 1e6
    return arr                       # already seconds


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _is_number(v):
    try:
        float(str(v).strip())
        return True
    except (TypeError, ValueError):
        return False


def _preview(arr, n=6):
    try:
        flat = np.asarray(arr).reshape(-1)[:n]
        return [_jsonable(v) for v in flat]
    except Exception:
        return []


def _jsonable(v):
    try:
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            f = float(v)
            return None if not np.isfinite(f) else f
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if isinstance(v, bytes):
            return v.decode("latin-1", "replace")
        if isinstance(v, float) and not np.isfinite(v):
            return None
        return v if isinstance(v, (int, float, str, bool, type(None))) else str(v)
    except Exception:
        return str(v)
