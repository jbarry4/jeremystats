"""Floor (stage) speed check, step 2: every measurement behind the check pages -> floor_check.pkl.

1. Ride windows in every session (the menu's rules, tracker center), with where and when each happened.
2. The true center of the turn, fitted per day (a rigid turn: velocity at right angles to the radius); the rides re-read
   about it.
3. Day readings: the menu's (median of rides), re-centered, rigid-fit, the peak of every 1-s angular speed, and the
   rides under 14 other settings.
4. Precision: bootstrap over mice, split halves, per-session readings and a half-hour reading per session.
5. Bias checks: readings by genotype, by session type, and against where on the circle the ride was.
6. The 10/7/2025 room + floor frame pair; the sessions where the tracker logged a motor change.
"""
import json
import os
import pickle
import time

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats as st

import floorlib as FL
from c1_floor_cache import read_full

T0 = time.time()
HERE = FL.HERE
A = pickle.load(open(os.path.join(HERE, "analysis.pkl"), "rb"))
MICE = A["MICE"]
F = FL.sessions().copy()
F["start_h"] = F.clock_h
F["geno"] = F.mouse.map(lambda m: MICE[m]["yh"] if m in MICE else "?")
F["age_group"] = F.mouse.map(lambda m: MICE[m]["age_group"] if m in MICE else "?")
DATES = sorted(F.date.unique())
OUT = {}


def log(*a):
    print("[%5.0fs]" % (time.time() - T0), *a, flush=True)


# ------------------------------------------------------------------ 1. ride windows, tracker center
TRK = {}
for r in F.itertuples():
    TRK[r.key] = FL.track(r.key)


def all_windows(centers=None, **kw):
    rows = []
    for r in F.itertuples():
        t, X, Y, lost = TRK[r.key]
        cx, cy = centers[r.date] if centers else (0.0, 0.0)
        w, info = FL.windows(t, X, Y, lost, cx=cx, cy=cy, detail=True, **kw)
        if not len(w):
            continue
        i1 = np.searchsorted(t, np.arange(kw.get("phase", 0.0), t[-1], 1.0))
        mid = i1[info[:, 3].astype(int) + kw.get("win", 4) // 2]
        ang_trk = np.degrees(np.arctan2(Y[mid], X[mid])) % 360
        rad_trk = np.hypot(X[mid], Y[mid])
        rows.append(pd.DataFrame(dict(key=r.key, date=r.date, mouse=r.mouse, session=r.session, geno=r.geno,
                                      t0=info[:, 0], abs_h=r.start_h + info[:, 0] / 3600.0, speed=w,
                                      radius=info[:, 1], angle=info[:, 2], angle_trk=ang_trk, radius_trk=rad_trk,
                                      idx=info[:, 3].astype(int))))
    return pd.concat(rows, ignore_index=True)


W0 = all_windows()
DAY0 = W0.groupby("date").speed.median()
ROT = json.load(open(os.path.join(HERE, "rotation_by_day.json")))
log("windows", len(W0), "max diff from the menu's day speeds %.1e" % max(abs(DAY0[d] - ROT["omega"][d]) for d in DATES))


# ------------------------------------------------------------------ 2. rigid fit per day, re-centered rides
def rigid_fit(segs):
    ra, rb = [], []
    for x, y in segs:
        vx, vy = np.diff(x), np.diff(y)
        mx, my = (x[1:] + x[:-1]) / 2, (y[1:] + y[:-1]) / 2
        ra += [np.c_[-my, np.ones_like(my), np.zeros_like(my)], np.c_[mx, np.zeros_like(mx), np.ones_like(mx)]]
        rb += [vx, vy]
    Am, b = np.vstack(ra), np.concatenate(rb)
    sol = np.linalg.lstsq(Am, b, rcond=None)[0]
    res = np.abs(Am @ sol - b)
    keep = res <= np.percentile(res, 90)
    w, p, q = np.linalg.lstsq(Am[keep], b[keep], rcond=None)[0]
    return float(np.degrees(w)), float(-q / w), float(p / w)


def segments(Wd):
    segs = []
    for key, g in Wd.groupby("key"):
        t, X, Y, _l = TRK[key]
        i1 = np.searchsorted(t, np.arange(0, t[-1], 1.0))
        for j in g.idx.values:
            ii = i1[j:j + 5]
            segs.append((X[ii], Y[ii]))
    return segs


CENTER, RIGID = {}, {}
for d in DATES:
    w, cx, cy = rigid_fit(segments(W0[W0.date == d]))
    CENTER[d], RIGID[d] = (cx, cy), w
# a second pass: re-select the rides about the fitted center and fit again (the selection used the tracker center)
W1 = all_windows(CENTER)
for d in DATES:
    w, cx, cy = rigid_fit(segments(W1[W1.date == d]))
    CENTER[d], RIGID[d] = (cx, cy), w
W1 = all_windows(CENTER)
DAY1 = W1.groupby("date").speed.median()
log("re-centered windows", len(W1))

# ------------------------------------------------------------------ 3. other day readings
VARIANTS = {  # name: (label, settings)
    "win3": ("3-s windows", dict(win=3)), "win6": ("6-s windows", dict(win=6)), "win8": ("8-s windows", dict(win=8)),
    "sd015": ("steadier: s.d. < 0.15", dict(sd_max=0.15)), "sd040": ("looser: s.d. < 0.40", dict(sd_max=0.40)),
    "dr02": ("radius change < 0.2 cm/s", dict(dr_max=0.2)), "dr08": ("radius change < 0.8 cm/s", dict(dr_max=0.8)),
    "lo10": ("speeds from 1.0 deg/s", dict(lo=1.0)), "hi12": ("speeds up to 12 deg/s", dict(hi=12.0)),
    "r8": ("from 8 cm out", dict(rmin=8.0)), "r20": ("from 20 cm out", dict(rmin=20.0)),
    "phase": ("1-s grid shifted 0.5 s", dict(phase=0.5)), "nolost": ("no lost frames inside", dict(drop_lost=True)),
    "strict": ("strict: 6 s, s.d. < 0.15, < 0.2 cm/s", dict(win=6, sd_max=0.15, dr_max=0.2)),
    "lenient": ("lenient: 3 s, s.d. < 0.4, < 0.8 cm/s, 1-12 deg/s", dict(win=3, sd_max=0.4, dr_max=0.8, lo=1.0, hi=12.0)),
}
DAYV, NV, SESSV = {}, {}, {}
for name, (_lab, kw) in VARIANTS.items():
    Wv = all_windows(**kw)
    DAYV[name] = Wv.groupby("date").speed.median()
    NV[name] = Wv.groupby("date").size()
    SESSV[name] = Wv.groupby("key").speed.agg(["median", "size"])
log("variants done")

# the peak of every 1-s angular speed (no ride rules at all), about the tracker center and the fitted center
MODE0, MODE1, STEPS = {}, {}, {}
for d in DATES:
    a0, a1 = [], []
    for k in F[F.date == d].key:
        t, X, Y, lost = TRK[k]
        a0.append(FL.angvel_steps(t, X, Y, lost))
        a1.append(FL.angvel_steps(t, X, Y, lost, cx=CENTER[d][0], cy=CENTER[d][1]))
    a0, a1 = np.concatenate(a0), np.concatenate(a1)
    MODE0[d], MODE1[d] = FL.kde_mode(a0), FL.kde_mode(a1)
    STEPS[d] = np.histogram(a1, bins=np.arange(-6, 12.01, 0.1))[0]
log("modes done")

# ------------------------------------------------------------------ 4. precision
rng = np.random.RandomState(11)
BOOT = {}
for lab, Wx in (("menu", W0), ("recentered", W1)):
    ci = {}
    for d in DATES:
        g = Wx[Wx.date == d]
        by = [v.speed.values for _m, v in g.groupby("mouse")]
        meds = []
        for _ in range(1000):
            pick = rng.randint(0, len(by), len(by))
            meds.append(np.median(np.concatenate([by[i] for i in pick])))
        ci[d] = (float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5)), float(np.std(meds)), len(by))
    BOOT[lab] = ci
log("bootstrap done")

# split halves by mice (days with at least 4 mice with rides)
SPLIT = []
for rep in range(300):
    a, b = {}, {}
    for d in DATES:
        g = W1[W1.date == d]
        ms = g.mouse.unique()
        if len(ms) < 4:
            continue
        perm = rng.permutation(ms)
        h1, h2 = perm[:len(ms) // 2], perm[len(ms) // 2:]
        a[d], b[d] = g[g.mouse.isin(h1)].speed.median(), g[g.mouse.isin(h2)].speed.median()
    ds = sorted(a)
    x, y = np.array([a[d] for d in ds]), np.array([b[d] for d in ds])
    SPLIT.append(dict(rep=rep, r=float(np.corrcoef(x, y)[0, 1]), mad=float(np.median(np.abs(x - y))), n_days=len(ds),
                      a=x if rep == 0 else None, b=y if rep == 0 else None, days=ds if rep == 0 else None))
r_med = float(np.median([s["r"] for s in SPLIT]))
log("split-half r %.4f, Spearman-Brown %.4f, median |half A - half B| %.3f deg/s" % (
    r_med, 2 * r_med / (1 + r_med), np.median([s["mad"] for s in SPLIT])))

# per-session readings and the half-hour reading (re-centered)
SESS = F[["key", "mouse", "session", "date", "start_h", "geno", "age_group", "use", "kind"]].copy()
g0, g1 = W0.groupby("key").speed, W1.groupby("key").speed
SESS["n0"], SESS["own0"] = SESS.key.map(g0.size()).fillna(0).astype(int), SESS.key.map(g0.median())
SESS["n1"], SESS["own1"] = SESS.key.map(g1.size()).fillna(0).astype(int), SESS.key.map(g1.median())
SESS["day0"], SESS["day1"] = SESS.date.map(DAY0), SESS.date.map(DAY1)


def local(Wx, d, mid_h, need=15):
    """Median of every reading that day within 30 min of the session's middle; with fewer than `need` there, the `need`
    readings nearest in time (so a session in a stall borrows its neighbors', not the whole day's)."""
    g = Wx[Wx.date == d]
    s = g[(g.abs_h >= mid_h - 0.5) & (g.abs_h <= mid_h + 0.5)]
    if len(s) >= need:
        return float(s.speed.median()), 0.5, len(s)
    near = g.iloc[np.argsort(np.abs(g.abs_h.values - mid_h))[:need]]
    return float(near.speed.median()), float(np.abs(near.abs_h - mid_h).max()), len(near)


for lab, Wx in (("0", W0), ("1", W1)):
    out = [local(Wx, r.date, r.start_h + 5 / 60.0) for r in SESS.itertuples()]
    SESS["local" + lab] = [o[0] for o in out]
    SESS["local_half" + lab] = [o[1] for o in out]
    SESS["local_n" + lab] = [o[2] for o in out]
log("half-hour readings: within 30 min", int((SESS.local_half1 == 0.5).sum()), "of", len(SESS))

# ------------------------------------------------------------------ 5. bias checks
MD = []
for lab, Wx, DAY in (("menu", W0, DAY0), ("recentered", W1, DAY1)):
    for (d, m), g in Wx.groupby(["date", "mouse"]):
        if len(g) < 5:
            continue
        others = Wx[(Wx.date == d) & (Wx.mouse != m)]
        if len(others) < 10:
            continue
        MD.append(dict(reading=lab, date=d, mouse=m, geno=MICE[m]["yh"], age_group=MICE[m]["age_group"], n=len(g),
                       own=float(g.speed.median()), others=float(others.speed.median()),
                       dev=float(g.speed.median() - others.speed.median())))
MD = pd.DataFrame(MD)
GENOBIAS = {}
for lab in ("menu", "recentered"):
    d = MD[MD.reading == lab]
    fit = smf.mixedlm("dev ~ C(geno, Treatment('WT'))", d, groups=d["date"]).fit()
    per_mouse = d.groupby(["mouse", "geno"]).dev.mean().reset_index()
    kw = st.kruskal(*[per_mouse[per_mouse.geno == g].dev.values for g in ("WT", "Het", "Hom")]).pvalue
    GENOBIAS[lab] = dict(p_het=float(fit.pvalues["C(geno, Treatment('WT'))[T.Het]"]),
                         p_hom=float(fit.pvalues["C(geno, Treatment('WT'))[T.Hom]"]),
                         b_het=float(fit.params["C(geno, Treatment('WT'))[T.Het]"]),
                         b_hom=float(fit.params["C(geno, Treatment('WT'))[T.Hom]"]), p_kw=float(kw),
                         mean=per_mouse.groupby("geno").dev.mean().to_dict(), sd=per_mouse.groupby("geno").dev.std().to_dict(),
                         n=per_mouse.groupby("geno").size().to_dict())
log("genotype bias", GENOBIAS)

# where on the circle: deviation of each ride from its day's reading, by the angle on screen (about the tracker center)
ANG = {}
for lab, Wx, DAY in (("menu", W0, DAY0), ("recentered", W1, DAY1)):
    dev = Wx.speed - Wx.date.map(DAY)
    b = (Wx.angle_trk // 30).astype(int)
    ANG[lab] = pd.DataFrame(dict(bin=b, dev=dev, period=Wx.date.map(lambda d: "2026 spring-summer" if "2026-03" <= d < "2026-10"
                                                                     else "other"))).groupby(["period", "bin"]).dev.agg(
        ["mean", "sem", "size"]).reset_index()
    fit = smf.ols("dev ~ np.cos(np.radians(a)) + np.sin(np.radians(a))", pd.DataFrame(dict(dev=dev, a=Wx.angle_trk))).fit()
    ANG[lab + "_amp"] = float(np.hypot(fit.params.iloc[1], fit.params.iloc[2]))
    ANG[lab + "_p"] = float(fit.f_pvalue)
log("angle dependence: amplitude menu %.3f, recentered %.3f deg/s" % (ANG["menu_amp"], ANG["recentered_amp"]))

# session type: habituation (s0) / day 1 / day 2 rides against the others that day
TYPE = []
for lab, Wx in (("menu", W0), ("recentered", W1)):
    for d in DATES:
        g = Wx[Wx.date == d]
        for ty, sel in (("s0", g.session == 0), ("training", g.session > 0)):
            if sel.sum() >= 5 and (~sel).sum() >= 10:
                TYPE.append(dict(reading=lab, date=d, type=ty, dev=float(g[sel].speed.median() - g[~sel].speed.median()),
                                 n=int(sel.sum())))
TYPE = pd.DataFrame(TYPE)

# ------------------------------------------------------------------ 6a. the 10/7/2025 pair
PD = r"C:\Users\Z390\Desktop\jeremystats\KCNT1 Active Avoidance\New Data\active_avoidance_data\KCNT1_DM_Feb24"
_h, R = read_full(os.path.join(PD, "M1S0_RoomTrack_Room_20251007_114827.dat"))
_h, Ar = read_full(os.path.join(PD, "M1S0_ArenaTrack_Arena_20251007_114827.dat"))
tp = (R["1msTimeStamp"].values - R["1msTimeStamp"].values[0]) / 1000.0
xr, yr = (R.RoomX.values - 127.5) / 3.122, -(R.RoomY.values - 127.5) / 3.122
xa, ya = (Ar.RoomX.values - 127.5) / 3.122, -(Ar.RoomY.values - 127.5) / 3.122
okp = ~((Ar.RoomX.values == 0) & (Ar.RoomY.values == 0))
th_r = np.degrees(np.unwrap(np.arctan2(yr[okp], xr[okp])))
th_a = np.degrees(np.unwrap(np.arctan2(ya[okp], xa[okp])))
phi = th_r - th_a
sl, ic = np.polyfit(tp[okp], phi, 1)
lostp = np.zeros(len(tp), bool)
wp0, ip0 = FL.windows(tp, xr, yr, lostp, detail=True)
Am = np.c_[2 * xr, 2 * yr, np.ones_like(xr)]
pcx, pcy, pc = np.linalg.lstsq(Am, xr ** 2 + yr ** 2, rcond=None)[0]
wp1 = FL.windows(tp, xr, yr, lostp, cx=pcx, cy=pcy)
i1p = np.searchsorted(tp, np.arange(0, tp[-1], 1.0))
prig = rigid_fit([(xr[i1p[j:j + 5]], yr[i1p[j:j + 5]]) for j in ip0[:, 3].astype(int)])
# how much did the object move on the floor during each ride window? (arena-frame angle change, deg/s)
th_a_full = np.degrees(np.unwrap(np.arctan2(ya, xa)))
creep = [float((th_a_full[i1p[j + 4]] - th_a_full[i1p[j]]) / (tp[i1p[j + 4]] - tp[i1p[j]])) for j in ip0[:, 3].astype(int)]
steps_p = FL.angvel_steps(tp, xr, yr, lostp)
PAIR = dict(t=tp[okp], phi=phi, slope=float(sl), intercept=float(ic), x=xr, y=yr, xa=xa[okp], ya=ya[okp],
            rides=wp0, rides_info=ip0, rides_recentered=wp1, center=(float(pcx), float(pcy)),
            circle_r=float(np.sqrt(pc + pcx ** 2 + pcy ** 2)), rigid=prig, creep=np.array(creep),
            mode=FL.kde_mode(steps_p), mean_step=float(np.mean(steps_p)),
            slope_about_center=float(np.polyfit(tp, np.degrees(np.unwrap(np.arctan2(yr - pcy, xr - pcx))), 1)[0]))
log("pair: direct %.3f, rides %.3f (n %d), re-centered %.3f, rigid %.3f, creep median %.3f deg/s" % (
    sl, np.median(wp0), len(wp0), np.median(wp1), prig[0], np.median(creep)))

# ------------------------------------------------------------------ 6b. motor changes logged by the tracker
MOT = {}
for r in F.itertuples():
    m = json.loads(r.motor)
    if m.get("4", 0) < 0.99 * sum(m.values()):
        _h, d = read_full(r.path)
        for c in ("1msTimeStamp", "RoomX", "RoomY", "State", "MotorState"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=["1msTimeStamp"])
        t = (d["1msTimeStamp"].values - d["1msTimeStamp"].values[0]) / 1000.0
        lost = d.State.values == 5
        x = pd.Series(np.where(lost, np.nan, d.RoomX.values)).ffill().bfill().values
        y = pd.Series(np.where(lost, np.nan, d.RoomY.values)).ffill().bfill().values
        X, Y = (x - 127.5) / 3.122, -(y - 127.5) / 3.122
        cx, cy = CENTER[r.date]
        w, info = FL.windows(t, X, Y, lost, lo=-9.0, hi=15.0, drop_lost=True, cx=cx, cy=cy, detail=True)
        mot = d.MotorState.values.astype(int)
        mt = mot[np.searchsorted(t, info[:, 0] + 2.0)] if len(w) else np.zeros(0)
        MOT[r.key] = dict(date=r.date, mouse=r.mouse, session=r.session, clock=r.hdr_time, t=t[::15], motor=mot[::15],
                          w=w, wt=info[:, 0] if len(w) else np.zeros(0), wmotor=mt,
                          secs={int(k): float((mot == int(k)).sum() * np.median(np.diff(t))) for k in np.unique(mot)})
log("motor sessions", len(MOT))

# ------------------------------------------------------------------ save
OUT = dict(W0=W0, W1=W1, DAY0=DAY0, DAY1=DAY1, CENTER=CENTER, RIGID=RIGID, VARIANTS=VARIANTS, DAYV=DAYV, NV=NV,
           SESSV=SESSV, MODE0=MODE0, MODE1=MODE1, STEPS=STEPS, BOOT=BOOT, SPLIT=SPLIT, SESS=SESS, MD=MD,
           GENOBIAS=GENOBIAS, ANG=ANG, TYPE=TYPE, PAIR=PAIR, MOT=MOT, DATES=DATES, ROT=ROT)
pickle.dump(OUT, open(os.path.join(HERE, "floor_check.pkl"), "wb"))
log("saved floor_check.pkl")
