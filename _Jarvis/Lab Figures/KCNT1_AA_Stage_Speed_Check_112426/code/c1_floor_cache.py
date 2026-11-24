"""Floor (stage) speed check, step 1: cache every session's raw track once (pixels, ms, state, motor, sectors, frame info).

Same session list as a1_extract (every used session plus the extra and repeat-habituation sessions). Writes
floor_cache.npz (per session: t_ms int32, px/py int16, state int8) and floor_sessions.csv (one row per session with
header facts and the values the tracker logged in its motor, sector and frame-info columns).
"""
import json
import os
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SESS = json.load(open(os.path.join(HERE, "sessions.json")))


def read_full(path):
    hdr, n_head = {}, 0
    with open(path, encoding="latin-1") as f:
        for n_head, line in enumerate(f, 1):
            s = line.strip()
            if s.startswith("%") and "(" in s:
                k = s[1:s.index("(")].strip().replace(".0", "")
                hdr[k] = s[s.index("(") + 1:s.rindex(")")].strip()
            if s.startswith("%%END_HEADER"):
                break
    fmt = hdr.get("Sample", "").split()
    d = pd.read_csv(path, sep=r"\s+", skiprows=n_head, header=None, engine="c", encoding="latin-1", comment="%")
    d.columns = fmt[:d.shape[1]] if len(fmt) >= d.shape[1] else list(range(d.shape[1]))
    return hdr, d


def main():
    t0 = time.time()
    use = [s for s in SESS if s["use"] or s["kind"] in ("Extra session beyond s16", "Repeat s0 (day-2 habituation)")]
    arrays, rows = {}, []
    for i, s in enumerate(use):
        h, d = read_full(s["path"])
        for c in ("FrameCount", "1msTimeStamp", "RoomX", "RoomY", "Sectors", "State", "CurrentLevel", "MotorState", "FrameInfo"):
            if c in d.columns and c != "Flags":
                d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=["1msTimeStamp"]).reset_index(drop=True)
        key = "%s_s%d%s" % (s["mouse"], s["session"], "" if s["use"] else "_x")
        arrays[key + "|t"] = d["1msTimeStamp"].values.astype(np.int64) - int(d["1msTimeStamp"].values[0])
        arrays[key + "|px"] = d["RoomX"].values.astype(np.int16)
        arrays[key + "|py"] = d["RoomY"].values.astype(np.int16)
        arrays[key + "|st"] = d["State"].values.astype(np.int8)
        mot = d["MotorState"].value_counts().to_dict()
        sec = d["Sectors"].value_counts().to_dict()
        fi = d["FrameInfo"].value_counts().to_dict() if "FrameInfo" in d.columns else {}
        rows.append(dict(key=key, mouse=s["mouse"], session=s["session"], day=s["day"], use=s["use"], kind=s["kind"],
                         when=s["when"], date=s["when"][:10], hdr_date=h.get("Date", ""), hdr_time=h.get("Time", ""),
                         elapsed_ms=h.get("ElapsedTime_ms", ""), center=h.get("ArenaCenterXY", ""),
                         pix_per_cm=h.get("TrackerResolution_PixPerCM", ""), diameter_m=h.get("ArenaDiameter_m", ""),
                         sector=h.get("ReinforcedSector", ""), frame=h.get("Frame", ""), tracker=h.get("TrackerVersion", ""),
                         n=len(d), motor=json.dumps({str(k): int(v) for k, v in mot.items()}),
                         sectors=json.dumps({str(k): int(v) for k, v in sec.items()}),
                         frameinfo=json.dumps({str(k): int(v) for k, v in fi.items()}), path=s["path"]))
        if i % 100 == 0:
            print(i, len(use), "%.0fs" % (time.time() - t0), flush=True)
    np.savez_compressed(os.path.join(HERE, "floor_cache.npz"), **arrays)
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "floor_sessions.csv"), index=False)
    print("done", len(rows), "sessions in %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
