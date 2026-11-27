"""How close in time DS and BTs sit to IEDs, over windows from 0.25 s to 60 s, against the same events moved to
random times (circular shifts within the session, 1,000 per mouse). Writes timing.pkl.

Pooled over the five IED+ mice: observed counts summed over mice, against the sum over mice of the same shift
number (shift s of every mouse together is one draw of the pooled chance distribution).
  ratio      observed / mean of the pooled chance draws
  chance band  2.5 to 97.5 percentiles of the pooled chance draws, over their mean
  p          share of pooled chance draws at or above the observed count (one-sided, more than chance)
  boot band  95% band of the ratio when the five mice are drawn again with replacement (2,000 times)
"""
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import menu_data as D  # noqa: E402

WINDOWS = np.array([0.25, 0.5, 1, 2, 5, 10, 20, 60])
IEDP = ["m13", "m28", "m3", "m5", "m34"]
N_SHIFT = 1000
rc = D.rc()
out = {"windows": WINDOWS, "mice": {}, "pooled": {}}
rng = np.random.RandomState(11)
for lab in IEDP:
    h = rc[(rc.wf == "halo") & (rc.lab == lab)]
    t0, t1 = float(h.t.min()), float(h.t.max())
    L = t1 - t0
    ti = np.sort(h[h.kind == "IED"].t.to_numpy())
    res = {}
    for k in ("DS", "TZ"):
        tk = np.sort(h[h.kind == k].t.to_numpy())
        near = np.array([np.min(np.abs(ti - t)) for t in tk])
        obs = np.array([(near <= w).sum() for w in WINDOWS])
        null = np.zeros((N_SHIFT, WINDOWS.size))
        for s in range(N_SHIFT):
            sh = t0 + ((tk - t0 + rng.uniform(5, L - 5)) % L)
            d = np.abs(sh[:, None] - ti[None, :]).min(axis=1)
            null[s] = [(d <= w).sum() for w in WINDOWS]
        res[k] = {"n": int(tk.size), "obs": obs, "null": null, "null_mean": null.mean(axis=0),
                  "p": ((null >= obs[None, :]).sum(axis=0) + 1) / (N_SHIFT + 1), "nearest": near}
    out["mice"][lab] = res
brng = np.random.RandomState(5)
for k in ("DS", "TZ"):
    obs = sum(out["mice"][l][k]["obs"] for l in IEDP).astype(float)
    null = sum(out["mice"][l][k]["null"] for l in IEDP)
    mu = null.mean(axis=0)
    boots = []
    for _ in range(2000):
        pick = brng.randint(0, len(IEDP), len(IEDP))
        o = sum(out["mice"][IEDP[i]][k]["obs"] for i in pick).astype(float)
        m = sum(out["mice"][IEDP[i]][k]["null_mean"] for i in pick)
        boots.append(o / np.maximum(m, 1e-9))
    boots = np.array(boots)
    out["pooled"][k] = {"obs": obs, "null_mean": mu, "ratio": obs / mu,
                        "chance_lo": np.percentile(null, 2.5, axis=0) / mu, "chance_hi": np.percentile(null, 97.5, axis=0) / mu,
                        "p": ((null >= obs[None, :]).sum(axis=0) + 1) / (N_SHIFT + 1),
                        "boot_lo": np.percentile(boots, 2.5, axis=0), "boot_hi": np.percentile(boots, 97.5, axis=0),
                        "n": int(sum(out["mice"][l][k]["n"] for l in IEDP))}
    P = out["pooled"][k]
    print(k, "ratio", P["ratio"].round(2), "p", P["p"].round(4), "chance hi", P["chance_hi"].round(2))
for lab in IEDP:
    r = out["mice"][lab]["TZ"]
    print(lab, "BT obs", r["obs"], "chance", r["null_mean"].round(1))
with open(os.path.join(HERE, "timing.pkl"), "wb") as f:
    pickle.dump(out, f, protocol=4)
