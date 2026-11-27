"""Candidate DS and IED events for the Methods figure, from Jarvis's curated sets (merged across machine shards)."""
import glob, gzip, json, os
import numpy as np, pandas as pd
GL = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\app\GUI_logs"
REC = {"m1606": dict(gid="s9a8f6138b49e", pooled="eda040008abc", inc="s9a8f6138b49e__36cd463250c19199718f.json.gz", dop="s9a8f6138b49e__96117d1d044dde65.json.gz"),
       "m306": dict(gid="s9619387fd35c", pooled="a1eb8aa0f5d1", inc="s9619387fd35c__2a4b6f4eedae45ce148d.json.gz", dop="s9619387fd35c__5ecb78879b930499.json.gz")}

def curation(gid, pooled):
    ev = {}
    for f in glob.glob(os.path.join(GL, "curation", "%s__poolede%s@*.json" % (gid, pooled))):
        j = json.load(open(f, encoding="utf-8"))
        for e in j.get("events", []):
            k = e["id"]
            if k not in ev or str(e.get("at", "")) > str(ev[k].get("at", "")): ev[k] = e
    return pd.DataFrame(ev.values())

out = {}
for name, r in REC.items():
    c = curation(r["gid"], r["pooled"])
    inc = json.load(gzip.open(r["inc"])); dop = json.load(gzip.open(r["dop"]))
    I = pd.DataFrame(inc["events"]); D = pd.DataFrame(dop["events"])
    print("==", name, "curation", c.shape, c.label.value_counts().to_dict(), "| origin x label:")
    print(pd.crosstab(c.origin, c.label))
    # attach detector features by nearest time
    c = c.sort_values("start").reset_index(drop=True)
    # one row per moment: entries within 5 ms are the same event re-banked (keep 'spike' if any copy says so)
    grp = np.r_[0, np.cumsum(np.diff(c.start.values) > 0.005)]
    rank = {"spike": 0, "likely_spike": 1, "flag": 2, "likely_garbage": 3, "garbage": 4}
    c["_r"] = c.label.map(rank).fillna(5)
    c["_g"] = grp
    orig = c.groupby("_g").origin.agg(lambda s: "both" if len(set(s)) > 1 else s.iloc[0])
    c = c.sort_values(["_g", "_r"]).groupby("_g").first().reset_index()
    c["origin"] = orig.values
    print(name, "after merging duplicates:", len(c), c.label.value_counts().to_dict())
    ti, td = I.start.values, D.start.values
    def near(t, arr):
        i = np.searchsorted(arr, t); best = None
        for j in (i - 1, i):
            if 0 <= j < len(arr) and (best is None or abs(arr[j] - t) < abs(arr[best] - t)): best = j
        return best
    feats = []
    for row in c.itertuples():
        t = row.start; ii = near(t, ti); dd = near(t, td)
        fi = I.iloc[ii] if ii is not None and abs(ti[ii] - t) < 0.025 else None
        fd = D.iloc[dd] if dd is not None and abs(td[dd] - t) < 0.025 else None
        feats.append(dict(inc_amp=(fi.amp if fi is not None else np.nan), inc_hw=(fi.half_width_ms if fi is not None else np.nan),
                          inc_ch=(fi.channel if fi is not None else np.nan), dop_peak=(fd.peak_uv if fd is not None else np.nan),
                          dop_nch=(fd.n_channels if fd is not None else np.nan), dop_ch=(fd.peak_channel if fd is not None else np.nan)))
    c = pd.concat([c, pd.DataFrame(feats)], axis=1)
    # isolation: time to the nearest other candidate (any label)
    t = c.start.values
    gap = np.full(len(t), np.inf)
    gap[1:] = np.minimum(gap[1:], np.diff(t)); gap[:-1] = np.minimum(gap[:-1], np.diff(t))
    c["iso_s"] = gap
    good = c[c.label == "spike"]
    ds = good[(good.origin == "incisor") & good.inc_amp.notna()].copy()
    ied = good[good.origin.isin(["doppler", "both"]) & good.dop_peak.notna()].copy()
    print(name, "DS candidates", len(ds), "amp med %.0f hw med %.1f" % (ds.inc_amp.median(), ds.inc_hw.median()),
          "| IED candidates", len(ied), "peak med %.0f nch med %.0f" % (ied.dop_peak.median(), ied.dop_nch.median()))
    # DS: standalone (>0.35 s from anything), closest to the median amplitude and half-width (robust z)
    d = ds[ds.iso_s > 0.35].copy()
    z = lambda x: (x - x.median()) / (1.4826 * (x - x.median()).abs().median())
    d["score"] = np.hypot(z(d.inc_amp), z(d.inc_hw))
    d = d.sort_values("score").head(40)
    # IED: standalone (>0.5 s), large and widespread: rank by peak and channel count
    e = ied[ied.iso_s > 0.5].copy()
    e["score"] = -(e.dop_peak.rank(pct=True) + e.dop_nch.rank(pct=True))
    e = e.sort_values("score").head(40)
    out[name] = dict(ds=d[["id", "start", "origin", "inc_amp", "inc_hw", "inc_ch", "iso_s"]].to_dict("records"),
                     ied=e[["id", "start", "origin", "dop_peak", "dop_nch", "dop_ch", "iso_s"]].to_dict("records"))
    print(name, "chosen DS", len(d), "IED", len(e)); print(e.head(5)[["start", "origin", "dop_peak", "dop_nch", "iso_s"]].to_string())
json.dump(out, open("candidates.json", "w"), indent=1, default=float)

# m1606 also has a dedicated curated DS set ('Dentate Spike', 326): candidates from it, isolated from every other event
DB = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\app\Data Bank\KCNT1\m1606\s1 2026-08-04"
f = [x for x in glob.glob(DB + "\ds - *.csv")][0]
dsc = pd.read_csv(f)
print("curated DS file", os.path.basename(f), dsc.shape, dsc.label.value_counts().to_dict())
inc = pd.DataFrame(json.load(gzip.open(REC["m1606"]["inc"]))["events"])
c = curation(REC["m1606"]["gid"], REC["m1606"]["pooled"])
allt = np.sort(np.r_[c.start.values, dsc.start_s.values])
rows = []
for t in dsc.start_s.values:
    j = np.argmin(np.abs(inc.start.values - t))
    if abs(inc.start.values[j] - t) > 0.01: continue
    others = allt[np.abs(allt - t) > 0.005]
    iso = np.min(np.abs(others - t)) if len(others) else np.inf
    rows.append(dict(start=float(t), inc_amp=float(inc.amp.values[j]), inc_hw=float(inc.half_width_ms.values[j]), inc_ch=int(inc.channel.values[j]), iso_s=float(iso)))
d = pd.DataFrame(rows)
d = d[d.iso_s > 0.35]
z = lambda x: (x - x.median()) / (1.4826 * (x - x.median()).abs().median())
d["score"] = np.hypot(z(d.inc_amp), z(d.inc_hw))
d = d.sort_values("score").head(40)
print("m1606 curated-DS candidates", len(d), "amp med %.0f hw %.1f" % (d.inc_amp.median(), d.inc_hw.median()))
out["m1606"]["ds_curated"] = d.to_dict("records")
json.dump(out, open("candidates.json", "w"), indent=1, default=float)
