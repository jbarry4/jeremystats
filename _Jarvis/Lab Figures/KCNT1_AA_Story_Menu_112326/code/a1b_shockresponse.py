"""Was the shock voltage really off in s0? A delivered shock makes a mouse jump: its speed in the half second after
the shock onset rises well above the half second before. Compare that jump in s0 with s1-s16, mouse by mouse."""
import json
import os

import numpy as np
import pandas as pd

import a1_extract as A

HERE = os.path.dirname(os.path.abspath(__file__))
SESS = [s for s in json.load(open(os.path.join(HERE, "sessions.json"))) if s["use"]]
rows = []
for s in SESS:
    h, d = A.read(s["path"])
    px = float(h["TrackerResolution_PixPerCM"])
    lost = d.state.values == 5
    x = pd.Series(np.where(lost, np.nan, d.x.values)).ffill().bfill().values / px
    y = pd.Series(np.where(lost, np.nan, d.y.values)).ffill().bfill().values / px
    t = (d.t_ms.values - d.t_ms.values[0]) / 1000.0
    st = pd.Series(np.where(lost, np.nan, d.state.values)).ffill().fillna(0).astype(int).values
    on = np.flatnonzero((st == 2) & (np.r_[-1, st[:-1]] != 2))
    sp = np.r_[0, np.hypot(np.diff(x), np.diff(y)) / np.maximum(np.diff(t), 1e-3)]          # cm/s, frame to frame
    sp = pd.Series(sp).rolling(5, center=True, min_periods=1).median().values
    pre, post = [], []
    for i in on:
        a = np.searchsorted(t, t[i] - 0.5)
        b = np.searchsorted(t, t[i] + 0.5)
        if a < i and b > i + 1:
            pre.append(np.mean(sp[a:i]))
            post.append(np.mean(sp[i:b]))
    pre, post = np.array(pre), np.array(post)
    rows.append(dict(mouse=s["mouse"], session=s["session"], n=len(pre),
                     jump=float(np.median(post - pre)) if pre.size else np.nan,
                     ratio=float(np.median(post / np.maximum(pre, 0.5))) if pre.size else np.nan))
df = pd.DataFrame(rows)
df.to_csv(os.path.join(HERE, "shock_response.csv"), index=False)
M = {m["mouse"]: m for m in json.load(open(os.path.join(HERE, "mice.json")))}
df["cohort"] = df.mouse.map(lambda m: M[m]["cohort"])
df["yh"] = df.mouse.map(lambda m: M[m]["yh"])
g = df.assign(block=np.where(df.session == 0, "s0", "s1-s16")).groupby(["cohort", "block"]).jump.median().unstack()
print(g.round(1).to_string())
piv = df.pivot_table(index="mouse", columns="session", values="jump")
s0 = piv[0]
tr = piv.loc[:, 1:16].median(axis=1)
out = pd.DataFrame({"s0_jump": s0, "train_jump": tr, "cohort": [M[m]["cohort"] for m in piv.index], "yh": [M[m]["yh"] for m in piv.index]})
out["s0_like_training"] = out.s0_jump > 0.5 * out.train_jump
print(out.sort_values("cohort").round(1).to_string())
out.to_csv(os.path.join(HERE, "s0_voltage_check.csv"))
