"""KCNT1 AA stage (floor) speed sanity check (2026-11-24): how the floor's turning speed is read from the mice, how far
the reading can be trusted, what its weak spots do to the menu, an outlier breakdown, and the menu's check table at one
floor speed and raw. Nine pages in the story-menu house style -> out_floor/, packaged to
Lab Figures/KCNT1_AA_Stage_Speed_Check_112426."""
import datetime
import glob
import os
import pickle
import shutil
import warnings

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import pymupdf
import statsmodels.formula.api as smf
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Rectangle
from scipy import stats as st

import figlib_aa as F
import floorlib as FL

warnings.filterwarnings("ignore")
OUT = os.path.join(F.HERE, "out_floor")
DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\KCNT1_AA_Stage_Speed_Check_112426"
F.FOOT = "KCNT1 active avoidance · stage (floor) speed check, a supplement to the story menu · exploratory, P uncorrected · 2026-11-24"
O = pickle.load(open(os.path.join(F.HERE, "floor_check.pkl"), "rb"))
CQ = pickle.load(open(os.path.join(F.HERE, "floor_conseq.pkl"), "rb"))
X = pickle.load(open(os.path.join(F.HERE, "floor_outliers.pkl"), "rb"))
W0, W1, DAY0, DAY1 = O["W0"], O["W1"], O["DAY0"], O["DAY1"]
DATES = O["DATES"]
SESS = O["SESS"]
MLIST = sorted(F.MICE, key=int)
RC = {"menu": F.INK, "recentered": "#1f6f8b", "halfhour": "#b07d2b", "refined": "#2a9d8f"}
YC = {2024: "#3d7ea6", 2026: "#c8a24a"}
RIDE = "#1f6f8b"
OFFS = np.array([np.hypot(*O["CENTER"][d]) for d in DATES])
OFFTXT = "%.1f-%.1f cm" % (OFFS.min(), OFFS.max())


def d2dt(d):
    return datetime.date.fromisoformat(d)


def pcell(p):
    if p is None or not np.isfinite(p):
        return "n/a"
    if 0.045 <= p < 0.055:            # keep 0.0498 and 0.0503 apart
        st_ = F.stars(p)
        return ("%.4f %s" % (p, st_)).strip()
    s = F.pstr(p).replace("P ", "")
    st_ = F.stars(p)
    return (s + " " + st_).strip()


def year_axes(fig, x, y, w, h, gap=0.25, split=0.5):
    """Two axes side by side for 2024 and 2026 day timelines."""
    a1 = F.axes_in(fig, x, y, w * split - gap / 2, h)
    a2 = F.axes_in(fig, x + w * split + gap / 2, y, w * (1 - split) - gap / 2, h)
    return a1, a2


# ============================================================================ page 2: how the floor speed is read
def page_method():
    fig, y = F.page("The floor's speed is read from the mice: a mouse that sits still rides along at the floor's speed",
                    "STAGE SPEED CHECK · 1 · HOW IT IS READ", number=2)
    key, j0 = "1644_s14", 287
    t, Xc, Yc, lost = FL.track(key)
    i1 = np.searchsorted(t, np.arange(0, t[-1], 1.0))
    seg = W0[(W0.key == key)]
    run = seg[(seg.idx >= j0) & (seg.idx <= j0 + 13)]
    k0, k1 = j0 - 28, j0 + 13 + 4 + 26
    ii = i1[k0:k1 + 1]
    tt = t[ii] - t[ii][0]
    xs, ys = Xc[ii], Yc[ii]
    th = np.degrees(np.unwrap(np.arctan2(ys, xs)))
    rad = np.hypot(xs, ys)
    a = np.diff(th)
    rs, re_ = j0 - k0, j0 - k0 + 13 + 4          # ride covers samples rs..re_ (14 windows of 4 s overlapping)
    reading = float(np.median(run.speed))
    y += 0.3
    F.letter(fig, 0.4, y, "a", "One mouse, 70 s: while it sat still for 17 s the floor carried it %.0f deg around the arena, "
                               "a reading of %.1f deg/s" % (th[re_] - th[rs], reading), width=7.6)
    # a1: the path in the arena (room frame)
    ax = F.axes_in(fig, 0.55, y + 0.25, 1.95, 1.95)
    F.arena(ax)
    full = (t >= t[ii][0]) & (t <= t[ii][-1])
    ax.plot(Xc[full], Yc[full], color=F.FAINT, lw=0.7, zorder=2)
    rr = (t >= t[ii][rs]) & (t <= t[ii][re_])
    ax.plot(Xc[rr], Yc[rr], color=RIDE, lw=2.4, zorder=3, solid_capstyle="round")
    ax.scatter(xs[rs:re_ + 1], ys[rs:re_ + 1], s=5, color="white", edgecolor=RIDE, lw=0.6, zorder=4)
    ax.scatter([xs[0]], [ys[0]], s=14, color=F.INK, zorder=4, marker="o")
    ax.text(xs[0] + 3, ys[0] - 3, "start", fontsize=5.5, color=F.SOFT, va="top")
    F.rot_arrow(ax, a0=200, a1=250)
    ax.text(0, -F.R_ARENA * 1.3, "Mouse 1644 (Het), s14, 10/29/2026: path in\nthe room (gray), the ride (blue; dots 1 s apart)",
            fontsize=5.5, color=F.SOFT, ha="center", va="top")
    # a2: angle against time
    ax = F.axes_in(fig, 3.0, y + 0.3, 2.15, 1.05)
    thf = np.degrees(np.unwrap(np.arctan2(Yc[full], Xc[full])))
    tf = t[full] - t[ii][0]
    rf = (tf >= tt[rs]) & (tf <= tt[re_])
    ax.plot(tf, thf, color=F.FAINT, lw=0.9)
    ax.plot(tf[rf], thf[rf], color=RIDE, lw=2.2)
    sl, ic = np.polyfit(tf[rf], thf[rf], 1)
    xx = np.array([tt[rs] - 6, tt[re_] + 6])
    ax.plot(xx, sl * xx + ic, color=F.INK, lw=0.6, ls="--")
    ax.text(tt[re_] + 3, sl * tt[re_] + ic - 10, "slope %.2f deg/s" % sl, fontsize=5.8, color=RIDE, va="top")
    ax.set_ylabel("Angle around\nthe arena (deg)")
    ax.set_xticklabels([])
    ax.axvspan(tt[rs], tt[re_], color=RIDE, alpha=0.07, lw=0)
    # a3: distance from the center
    ax2 = F.axes_in(fig, 3.0, y + 1.45, 2.15, 0.75)
    ax2.plot(tt, rad, color=F.FAINT, lw=0.9)
    ax2.plot(tt[rs:re_ + 1], rad[rs:re_ + 1], color=RIDE, lw=2.2)
    ax2.axvspan(tt[rs], tt[re_], color=RIDE, alpha=0.07, lw=0)
    ax2.set_ylabel("From the\ncenter (cm)")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylim(0, 45)
    # a4: the 1-s angle speeds against the rules
    ax3 = F.axes_in(fig, 5.75, y + 0.3, 2.1, 1.05)
    ta = (tt[1:] + tt[:-1]) / 2
    ax3.bar(ta, a, width=0.8, color=[RIDE if rs <= k < re_ else "#c9ccd3" for k in range(len(a))], lw=0)
    ax3.axhspan(1.5, 9, color="#eef3f6", zorder=0, lw=0)
    ax3.axhline(0, color=F.FAINT, lw=0.5)
    ax3.set_ylim(-25, 30)
    ax3.set_ylabel("1-s angle speed\n(deg/s)")
    ax3.set_xticklabels([])
    ax3.text(tt[-1], 27, "steady while riding", fontsize=5.5, color=RIDE, ha="right", va="top")
    dr = np.abs(np.diff(rad))
    ax4 = F.axes_in(fig, 5.75, y + 1.45, 2.1, 0.75)
    ax4.bar(ta, dr, width=0.8, color=[RIDE if rs <= k < re_ else "#c9ccd3" for k in range(len(a))], lw=0)
    ax4.axhline(0.4, color=F.ZONE, lw=0.6, ls="--")
    ax4.text(tt[-1], 0.5, "0.4 cm", fontsize=5.3, color=F.ZONE, ha="right", va="bottom")
    ax4.set_yscale("symlog", linthresh=0.5)
    ax4.set_yticks([0, 0.4, 2, 10])
    ax4.set_yticklabels(["0", "0.4", "2", "10"])
    ax4.set_ylabel("Radius change\n(cm per s)")
    ax4.set_xlabel("Time (s)")
    yr = y + 2.6
    F.put(fig, 0.55, yr,
          "The rules for one reading (as in the menu): four 1-s steps in a row in which the distance from the center changes by "
          "less than 0.4 cm a second, the four angle speeds vary by less than 0.25 deg/s (s.d.), their mean lies between 1.5 "
          "and 9 deg/s, and the mouse is more than 12 cm from the center. Each passing 4-s stretch is one reading; stretches "
          "slide by 1 s, so this 17-s ride gave %d readings (median %.2f deg/s). Positions are the tracker's own, about the "
          "tracker's arena center." % (len(run), reading), 7.3, size=6.4, color=F.SOFT)
    # b: three days
    yb = yr + 0.85
    F.letter(fig, 0.4, yb, "b", "A day's speed is the median of every reading that day, all mice pooled: three days, three "
                                "floor speeds", width=7.6)
    for k, d in enumerate(["2024-05-13", "2024-10-08", "2026-03-20"]):
        ax = F.axes_in(fig, 0.75 + k * 2.45, yb + 0.3, 2.05, 1.25)
        v = W0[W0.date == d].speed.values
        ax.hist(v, bins=np.arange(1.5, 9.01, 0.1), color=YC[int(d[:4])], lw=0)
        ax.axvline(np.median(v), color=F.INK, lw=1.0)
        ax.text(np.median(v) + 0.15, ax.get_ylim()[1] * 0.95, "%.2f deg/s" % np.median(v), fontsize=6.2, weight="bold", va="top")
        ax.set_title("%s · %d readings, %d mice" % (d2dt(d).strftime("%b %-d, %Y") if os.name != "nt" else d2dt(d).strftime("%b %#d, %Y"),
                                                   len(v), W0[W0.date == d].mouse.nunique()), fontsize=6.0, loc="left")
        ax.set_xlim(1.5, 8)
        ax.set_xlabel("Reading (deg/s)")
        if k == 0:
            ax.set_ylabel("Readings")
    # c: from days to a mouse
    yc = yb + 2.3
    F.letter(fig, 0.4, yc, "c", "A mouse's speed is the median over its 17 sessions; with 9 of them on day 1, that is its day-1 "
                                "speed", width=7.6)
    ax = F.axes_in(fig, 0.75, yc + 0.3, 3.3, 1.45)
    U = SESS[SESS.use]
    for m, col in (("457", "#e08a2c"), ("1634", "#7b2d8e"), ("1652", "#8c8c8c")):
        g = U[U.mouse == m].sort_values("session")
        ax.plot(g.session, g.day0, color=col, lw=0.8, marker="o", ms=3)
        ax.axhline(F.MICE[m]["omega"], color=col, lw=0.6, ls=":")
        ax.text(16.4, F.MICE[m]["omega"], "%s (%s): %.2f" % (m, F.geno(m), F.MICE[m]["omega"]), fontsize=5.6, color=col, va="center")
    ax.axvline(8.5, color=F.FAINT, lw=0.5)
    ax.text(4.2, 6.15, "day 1 (s0-s8)", fontsize=5.6, color=F.SOFT, ha="center")
    ax.text(12.5, 6.15, "day 2 (s9-s16)", fontsize=5.6, color=F.SOFT, ha="center")
    ax.set_ylim(2.4, 6.4)
    ax.set_xlim(-0.5, 16.3)
    ax.set_xticks([0, 4, 8, 12, 16])
    ax.set_xlabel("Session")
    ax.set_ylabel("Floor speed used (deg/s)")
    F.put(fig, 5.55, yc + 0.32,
          "Each session takes its day's reading; the mouse takes the median of its sessions (dotted). Mouse 457's day 2 "
          "read 0.5 deg/s faster than its day 1, but its speed is the day-1 value. Session values (curves, mixed models, "
          "entrances per turn) use the session's own day; per-mouse values use the mouse's speed. 12,188 readings over 44 "
          "days (55-1,033 a day, median %d); 87 of 958 sessions gave none (mostly habituation, when mice rarely sit still) "
          "and take their day's reading." % int(W0.groupby("date").size().median()), 2.35, size=6.3, color=F.INK)
    F.save(fig, OUT, "02_how_it_is_read")


# ============================================================================ page 3: two known answers
def page_known():
    fig, y = F.page("Two checks with known answers: the reading matches a direct measurement and follows the motor",
                    "STAGE SPEED CHECK · 2 · KNOWN ANSWERS", number=3)
    P = O["PAIR"]
    rides, creep = P["rides"], P["creep"]
    y += 0.3
    F.letter(fig, 0.4, y, "a", "On the one day both frames were saved (10/7/2025), the floor turned at %.2f deg/s; the rides read "
                               "%.2f because the mouse crept forward on the floor, and read %.2f once its creep is taken out"
             % (P["slope"], np.median(rides), np.median(rides - creep)), width=7.6)
    ax = F.axes_in(fig, 0.75, y + 0.35, 2.2, 1.45)
    ax.plot(P["t"], P["phi"] - P["phi"][0], color=F.INK, lw=0.8)
    tt = np.array([P["t"].min(), P["t"].max()])
    ax.plot(tt, P["slope"] * tt + P["intercept"] - P["phi"][0], color=F.KICK, lw=0.8, ls="--")
    ax.set_xlabel("Time in the session (s)")
    ax.set_ylabel("Floor angle (deg)")
    ax.set_title("Direct: room angle minus floor-frame angle\ngrows at %.2f deg/s (3.2 turns)" % P["slope"], fontsize=6, loc="left")
    ax = F.axes_in(fig, 3.45, y + 0.35, 2.0, 1.45)
    xx = np.array([-0.5, 0.75])
    ax.plot(xx, P["slope"] + xx, color=F.KICK, lw=0.8, ls="--")
    ax.text(0.72, 3.95, "line: the floor's %.2f + creep" % P["slope"], fontsize=5.6, color=F.KICK, ha="right", va="bottom")
    ax.scatter(creep, rides, s=16, color=RIDE, edgecolor="white", lw=0.4, zorder=3)
    ax.axhline(P["slope"], color=F.FAINT, lw=0.5, ls=":")
    ax.set_xlabel("The mouse's own movement on the\nfloor during the ride (deg/s)")
    ax.set_ylabel("Ride reading (deg/s)")
    ax.set_title("The 10 readings follow floor + creep", fontsize=6, loc="left")
    ax = F.axes_in(fig, 6.0, y + 0.35, 1.75, 1.45)
    vals = [P["slope"], np.median(rides), np.median(rides - creep), P["rigid"][0]]
    labs = ["direct", "rides", "rides\nminus creep", "rigid-turn\nfit"]
    ax.bar(range(4), vals, color=[F.KICK, RIDE, "#9ec5d6", "#c9ccd3"], width=0.65)
    for k, v in enumerate(vals):
        ax.text(k, v + 0.03, "%.2f" % v, ha="center", fontsize=5.8)
    ax.set_ylim(4.0, 4.75)
    ax.set_xticks(range(4))
    ax.set_xticklabels(labs, fontsize=5.4)
    ax.set_ylabel("deg/s")
    F.put(fig, 0.75, y + 2.4,
          "That day (M1, s0) the tracker also saved the floor frame, so the floor's angle is known at every frame. The "
          "mouse sat at one spot for 4.5 min but crept forward by a median %.2f deg/s during the 10 readings; the readings "
          "equal the floor's speed plus that creep. Across many mice creeping goes both ways and is not tied to genotype "
          "(page 5); this one day cannot say whether it averages to exactly zero, so the absolute speeds carry a few-percent "
          "uncertainty that applies to every mouse alike." % np.median(creep), 7.0, size=6.3, color=F.SOFT)
    # b: motor log
    yb = y + 3.25
    M = O["MOT"]
    F.letter(fig, 0.4, yb, "b", "When the tracker's motor log changed, the readings followed: 0.0 deg/s while it read 'off' "
                                "and 1.5 times faster while it read 7 instead of the usual 4", width=7.6)
    shows = [("522_s2", "Mouse 522, s2 (4/10/2026)"), ("1663_s16", "Mouse 1663, s16 (11/7/2026)"),
             ("1649_s7", "Mouse 1649, s7 (10/28/2026)"), ("526_s12", "Mouse 526, s12 (3/14/2026)")]
    MC = {0: "#f2d0d0", 4: None, 7: "#d4e6ce", 5: "#d4e6ce", 6: "#d4e6ce", 1: "#f6e3c4", 2: "#f6e3c4", 3: "#f6e3c4"}
    for k, (key, title) in enumerate(shows):
        r, c = divmod(k, 2)
        ax = F.axes_in(fig, 0.75 + c * 3.65, yb + 0.4 + r * 2.0, 3.15, 1.4)
        mm = M[key]
        mot, tm = mm["motor"], mm["t"]
        ch = np.flatnonzero(np.diff(mot) != 0)
        starts = np.r_[0, ch + 1]
        ends = np.r_[ch, len(mot) - 1]
        for s0, e0 in zip(starts, ends):
            col = MC.get(int(mot[s0]), "#eeeeee")
            if col and tm[e0] - tm[s0] > 1:
                ax.axvspan(tm[s0], tm[e0], color=col, lw=0, zorder=0)
                if tm[e0] - tm[s0] > 30:
                    ax.text((tm[s0] + tm[e0]) / 2, 10.6, "log %d" % mot[s0], fontsize=5.2, ha="center", va="top", color=F.SOFT)
        w, wt, wm = mm["w"], mm["wt"], mm["wmotor"]
        ax.scatter(wt + 2, w, s=9, color=[F.ZONE if m_ == 0 else ("#4a8b3c" if m_ >= 5 else RIDE) for m_ in wm], lw=0, zorder=3)
        dday = DAY1[mm["date"]]
        ax.axhline(dday, color=F.INK, lw=0.5, ls=":")
        ax.text(598, dday + 0.25, "day %.1f" % dday, fontsize=5.2, ha="right", color=F.SOFT)
        ax.set_ylim(-1, 11)
        ax.set_xlim(0, 600)
        med = {int(v): float(np.median(w[wm == v])) for v in np.unique(wm)}
        txt = ", ".join("log %d reads %.1f" % (v, s) for v, s in sorted(med.items()) if (wm == v).sum() >= 2)
        ax.set_title("%s · %s deg/s" % (title, txt), fontsize=6.0, loc="left")
        ax.set_ylabel("Reading (deg/s)")
        if r == 1:
            ax.set_xlabel("Time in the session (s)")
    F.put(fig, 0.75, yb + 4.25,
          "Mouse 522's s2 is where the 4/10/2026 step on page 6 happened: the floor crawled at 1.9 deg/s, the motor was "
          "switched off for 28 s, and it came back at 3.4. Readings here drop the 1.5-9 deg/s limit so a stopped floor can show. Shading: the motor value the tracker logged "
          "(red 'off' = 0, green = above 4, tan = 1-3); dots: readings, red while the log read 0. The log read 4 in 99.8% of "
          "all frames on every day, at floor speeds from 2.2 to 5.8 deg/s: it records the setting, not the speed. Ten "
          "sessions logged something else for a while: 20-70 s of 'off' in seven, a reversal in the last 15-32 s of two "
          "(477 s4, 479 s4), and mouse 1649 ran 8 of its 10 s7 minutes at 7.", 7.0, size=6.3, color=F.SOFT)
    F.save(fig, OUT, "03_known_answers")


# ============================================================================ page 4: robust to the rules
def page_rules():
    fig, y = F.page("The reading barely moves when the ride rules change, and two methods without rules agree with it",
                    "STAGE SPEED CHECK · 3 · ROBUST TO THE RULES", number=4)
    y += 0.3
    order = ["win3", "win6", "win8", "sd015", "sd040", "dr02", "dr08", "lo10", "hi12", "r8", "r20", "phase", "nolost",
             "lenient"]
    rows = []
    for name in order:
        dv = O["DAYV"][name].reindex(DAY0.index)
        d = (dv - DAY0).dropna()
        rows.append((name, O["VARIANTS"][name][0], d.values, int(O["NV"][name].reindex(DAY0.index).fillna(0).median()),
                     len(d)))
    meds = [np.median(np.abs(r[2])) for r in rows]
    F.letter(fig, 0.4, y, "a", "Changing one rule at a time moves a day's reading by a median of %.2f-%.2f deg/s; only the "
                               "6- and 8-s windows, which leave few rides, move single days more" % (min(meds), max(meds)),
             width=7.6)
    ax = F.axes_in(fig, 2.55, y + 0.35, 3.6, 3.7)
    rng = np.random.RandomState(1)
    for k, (name, lab, d, n, nd) in enumerate(rows):
        ax.scatter(d, k + (rng.rand(d.size) - 0.5) * 0.35, s=6, color=F.KICK, alpha=0.7, lw=0)
        ax.plot([np.median(d)] * 2, [k - 0.3, k + 0.3], color=F.INK, lw=1.2)
        ax.text(-1.06, k, lab, fontsize=6.0, ha="right", va="center")
        ax.text(1.04, k, "%d" % n + ("" if nd == 44 else " (%d days)" % nd), fontsize=5.8, va="center", color=F.SOFT)
    ax.axvline(0, color=F.FAINT, lw=0.6)
    for v in (-0.25, 0.25):
        ax.axvline(v, color=F.GRID, lw=0.6, ls="--", zorder=0)
    ax.set_xlim(-1.0, 1.0)
    ax.set_ylim(len(rows) - 0.4, -0.6)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Change in each day's reading from the menu's (deg/s)")
    ax.text(1.04, -0.9, "readings\nper day", fontsize=5.6, color=F.SOFT, va="bottom")
    ax.text(-1.06, -0.9, "Rule changed (the menu's: 4 s, s.d. < 0.25,\n< 0.4 cm/s, 1.5-9 deg/s, > 12 cm)", fontsize=5.6,
            color=F.SOFT, ha="right", va="bottom")
    # b: methods without the rules
    yb = y + 4.85
    pk0, rg = pd.Series(O["MODE0"]), pd.Series(O["RIGID"])
    F.letter(fig, 0.4, yb, "b", "Two readings that use no ride rules track the menu's day by day (r %.3f and %.3f); both sit "
                                "a little higher" % (np.corrcoef(pk0[DAY0.index], DAY0)[0, 1], np.corrcoef(rg[DAY0.index], DAY0)[0, 1]),
             width=7.6)
    for k, (ser, title, note) in enumerate((
            (pk0, "Peak of every 1-s angle speed", "every step of every mouse > 10 cm from the center, no rules; the peak "
                                                  "is where still mice pile up"),
            (rg, "Rigid-turn fit", "a turn's speed and center fitted to the rides' motion (velocity at right angles to "
                                   "the radius), so it does not use the tracker's center"))):
        ax = F.axes_in(fig, 0.75 + k * 3.7, yb + 0.35, 1.9, 1.9)
        for d in DATES:
            ax.scatter(DAY0[d], ser[d], s=13, color=YC[int(d[:4])], edgecolor="white", lw=0.4, zorder=3)
        ax.plot([1.8, 6.5], [1.8, 6.5], color=F.FAINT, lw=0.6, ls="--")
        ax.set_xlim(1.8, 6.5)
        ax.set_ylim(1.8, 6.5)
        ax.set_aspect("equal")
        ax.set_xlabel("Menu's day reading (deg/s)")
        ax.set_ylabel("%s (deg/s)" % title.split(" ")[0] if k == 0 else "Rigid-turn fit (deg/s)")
        dd = (ser[DAY0.index] - DAY0)
        ax.set_title(title, fontsize=6.3, loc="left")
        F.put(fig, 2.8 + k * 3.7, yb + 0.45, "%s. Difference from the menu's: median %+.2f deg/s, largest %.2f." % (
            note[0].upper() + note[1:], dd.median(), dd.abs().max()), 1.4, size=6.0, color=F.SOFT)
    hs = [Line2D([], [], ls="", marker="o", ms=4, mfc=YC[2024], mec="white", label="2024 day"),
          Line2D([], [], ls="", marker="o", ms=4, mfc=YC[2026], mec="white", label="2026 day")]
    W, H = fig.get_size_inches()
    fig.legend(handles=hs, frameon=False, fontsize=5.8, loc="upper left", ncol=2, bbox_to_anchor=(0.75 / W, 1 - (yb + 2.75) / H))
    F.put(fig, 0.75, yb + 3.05,
          "Why both sit higher: the rigid-turn fit finds the floor turning about a point %s from the tracker's center, "
          "mostly below it (page 6). Angles taken about the wrong point read slow on the side where the mice mostly sit, so the "
          "menu's readings run a little low on the days with the largest offset. The fit's own speed tracks the menu's "
          "within %.2f deg/s on the median day." % (OFFTXT, (rg[DAY0.index] - DAY0).abs().median()), 7.0, size=6.3, color=F.SOFT)
    F.save(fig, OUT, "04_robust_to_rules")


# ============================================================================ page 5: precise and unbiased
def page_precise():
    fig, y = F.page("Each day's reading is precise, two mice on the same day agree, and the genotype of the mouse "
                    "riding does not matter", "STAGE SPEED CHECK · 4 · PRECISE AND UNBIASED", number=5)
    B = O["BOOT"]["menu"]
    wid = np.array([B[d][1] - B[d][0] for d in DATES])
    y += 0.3
    F.letter(fig, 0.4, y, "a", "Resampling the mice leaves each day's reading within ±%.2f deg/s (median 95%% range), "
                               "against a %.1f deg/s spread between days" % (np.median(wid) / 2, DAY0.std()), width=7.6)
    for k, yr in enumerate(("2024", "2026")):
        ds = [d for d in DATES if d.startswith(yr)]
        ax = F.axes_in(fig, 0.75 + k * 3.65, y + 0.35, 3.15, 1.45)
        for d in ds:
            x = d2dt(d)
            ax.plot([x, x], [B[d][0], B[d][1]], color=YC[int(yr)], lw=2.6, solid_capstyle="butt")
            ax.scatter([x], [DAY0[d]], s=3, color=F.INK, zorder=3)
        ax.set_ylim(1.5, 6.5)
        ax.set_title(yr, fontsize=6.5, loc="left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.tick_params(axis="x", labelsize=5.6)
        if k == 0:
            ax.set_ylabel("Day reading (deg/s)")
    widest = sorted(((B[d][1] - B[d][0], d) for d in DATES), reverse=True)[:2]
    F.put(fig, 0.75, y + 2.05,
          "Dot: the day's reading; bar: 95%% range over 1,000 redraws of that day's mice. Widest: %s (%.2f deg/s, %d "
          "readings from 4 mice) and %s (%.2f). Measurement scatter is about %.1f%% of the between-day variance."
          % (widest[0][1], widest[0][0], len(W0[W0.date == widest[0][1]]), widest[1][1], widest[1][0],
             100 * np.mean([B[d][2] ** 2 for d in DATES]) / DAY0.var()), 7.0, size=6.3, color=F.SOFT)
    # b: two mice on the same day
    yb = y + 2.75
    MD = O["MD"]
    m0 = MD[MD.reading == "menu"]
    pairs = []
    for d, g in m0.groupby("date"):
        v = g.sort_values("mouse")
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                pairs.append((d, v.own.iloc[i], v.own.iloc[j], v.mouse.iloc[i], v.mouse.iloc[j]))
    pa = np.array([p[1] for p in pairs])
    pb = np.array([p[2] for p in pairs])
    F.letter(fig, 0.4, yb, "b", "Two different mice on the same day read the same floor: r %.3f over %d pairs, median "
                                "difference %.2f deg/s" % (np.corrcoef(pa, pb)[0, 1], len(pairs), np.median(np.abs(pa - pb))),
             width=7.6)
    ax = F.axes_in(fig, 0.75, yb + 0.35, 2.0, 2.0)
    for p in pairs:
        ax.scatter(p[1], p[2], s=10, color=YC[int(p[0][:4])], edgecolor="white", lw=0.3, zorder=3)
    ax.plot([1.5, 6.6], [1.5, 6.6], color=F.FAINT, lw=0.6, ls="--")
    ax.set_xlim(1.5, 6.6)
    ax.set_ylim(1.5, 6.6)
    ax.set_aspect("equal")
    ax.set_xlabel("Mouse A's own reading (deg/s)")
    ax.set_ylabel("Mouse B's, same day (deg/s)")
    ax = F.axes_in(fig, 3.35, yb + 0.35, 1.8, 2.0)
    ax.hist(pa - pb, bins=np.arange(-1.5, 1.51, 0.1), color=F.KICK, lw=0)
    ax.set_xlabel("A minus B (deg/s)")
    ax.set_ylabel("Pairs")
    F.put(fig, 5.6, yb + 0.4,
          "Each mouse-day with at least 5 readings of its own (%d mouse-days); every pair of mice run on the same day. "
          "The largest gaps come from days the floor changed speed between one mouse's run and the next (page 6)."
          % len(m0), 2.3, size=6.3, color=F.SOFT)
    # c: genotype
    yc = yb + 2.95
    gb = O["GENOBIAS"]
    F.letter(fig, 0.4, yc, "c", "Het and Hom mice read the floor no differently from WT (P %.2f, %.2f), so the speed does not "
                                "carry the genotype in with it" % (gb["menu"]["p_het"], gb["menu"]["p_hom"]), width=7.6)
    for k, lab in enumerate(("menu", "recentered")):
        ax = F.axes_in(fig, 0.75 + k * 2.9, yc + 0.35, 2.3, 1.6)
        d = MD[MD.reading == lab].groupby("mouse").dev.mean()
        rng = np.random.RandomState(3)
        for gi, g in enumerate(("WT", "Het", "Hom")):
            ms = [m for m in d.index if F.geno(m) == g]
            ax.plot([gi - 0.3, gi + 0.3], [np.median(d[ms])] * 2, color=F.INK, lw=1.2, zorder=3)
            for m in ms:
                F.scatter_mouse(ax, gi + (rng.rand() - 0.5) * 0.36, d[m], m, size=16)
            for m in [m for m in ms if abs(d[m]) > 0.3]:
                ax.text(gi + 0.22, d[m], m, fontsize=5, color=F.SOFT, va="center")
        ax.axhline(0, color=F.FAINT, lw=0.6)
        lim = max(0.6, float(d.abs().max()) + 0.08)
        ax.set_ylim(-lim, lim)
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(["WT", "Het", "Hom"])
        ax.set_xlim(-0.6, 2.6)
        ax.tick_params(axis="x", length=0)
        ax.set_ylabel("Own reading minus the\nother mice's, same day (deg/s)")
        g = gb[lab]
        ax.set_title(("About the tracker's center (the menu)" if lab == "menu" else "About the floor's true center") +
                     "\nHet vs WT %s · Hom vs WT %s" % (F.pstr(g["p_het"]), F.pstr(g["p_hom"])), fontsize=5.9, loc="left")
    F.put(fig, 6.65, yc + 0.4,
          "One dot per mouse: its own median reading minus the other mice's that day, averaged over its days. Mixed model "
          "with day as a random effect; Kruskal-Wallis P %.2f (menu) and %.2f (true center). About the true center the "
          "spread shrinks: part of what looked like mouse-to-mouse differences was where on the circle each mouse sat."
          % (gb["menu"]["p_kw"], gb["recentered"]["p_kw"]), 1.35, size=6.0, color=F.SOFT)
    F.save(fig, OUT, "05_precise_unbiased")


# ============================================================================ page 6: what one number per day misses
def page_misses():
    fig, y = F.page("What one number per day misses: the floor turns about an off-center point, and on some days it "
                    "changed speed mid-day", "STAGE SPEED CHECK · 5 · WEAK SPOTS", number=6)
    y += 0.3
    cen = O["CENTER"]
    offs = np.array([np.hypot(*cen[d]) for d in DATES])
    F.letter(fig, 0.4, y, "a", "The floor turns about a point %.1f-%.1f cm from the tracker's center, mostly below it; rides on "
                               "the far side read slow, and re-centering lifts days by a median %.2f deg/s"
             % (offs.min(), offs.max(), np.median(DAY1 - DAY0)), width=7.6)
    ax = F.axes_in(fig, 0.55, y + 0.3, 1.9, 1.9)
    ax.add_patch(Circle((0, 0), 6, fill=False, ec="#d5d8de", lw=0.5))
    ax.add_patch(Circle((0, 0), 3, fill=False, ec="#d5d8de", lw=0.5))
    ax.plot([-6.5, 6.5], [0, 0], color="#e6e8ec", lw=0.5)
    ax.plot([0, 0], [-6.5, 6.5], color="#e6e8ec", lw=0.5)
    for d in DATES:
        ax.scatter(cen[d][0], cen[d][1], s=12, color=YC[int(d[:4])], edgecolor="white", lw=0.3, zorder=3)
    ax.scatter([0], [0], marker="+", s=50, color=F.INK, zorder=4)
    pc = O["PAIR"]["center"]
    ax.scatter([pc[0]], [pc[1]], marker="x", s=22, color=F.ZONE, zorder=4)
    ax.text(pc[0], pc[1] + 0.7, "10/7/2025", fontsize=5, color=F.ZONE, ha="center")
    ax.text(0, 6.3, "3 and 6 cm rings", fontsize=5.0, color=F.SOFT, ha="center")
    ax.set_xlim(-6.8, 6.8)
    ax.set_ylim(-6.8, 6.8)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Fitted center of each day (+ = tracker's)", fontsize=6, loc="left")
    ax = F.axes_in(fig, 3.0, y + 0.35, 2.3, 1.45)
    for lab, col, mk in (("menu", RC["menu"], "o"), ("recentered", RC["recentered"], "s")):
        A_ = O["ANG"][lab]
        g = A_.groupby("bin").apply(lambda q: np.average(q["mean"], weights=q["size"]))
        ax.plot(g.index * 30 + 15, g.values, color=col, marker=mk, ms=3, lw=1)
    ax.axhline(0, color=F.FAINT, lw=0.5)
    ax.axvspan(15, 75, color=F.ZONE, alpha=0.1, lw=0)
    ax.set_xticks([0, 90, 180, 270, 360])
    ax.set_xlabel("Where the ride was, angle on screen (deg)")
    ax.set_ylabel("Ride minus its day (deg/s)")
    ax.legend(handles=[Line2D([], [], color=RC["menu"], marker="o", ms=3, label="tracker's center (menu)"),
                       Line2D([], [], color=RC["recentered"], marker="s", ms=3, label="floor's true center")],
              frameon=False, fontsize=5.4, loc="upper right")
    ax.set_title("Swing around the circle: %.2f vs %.2f deg/s" % (O["ANG"]["menu_amp"], O["ANG"]["recentered_amp"]),
                 fontsize=6, loc="left")
    ax = F.axes_in(fig, 6.0, y + 0.35, 1.9, 1.45)
    for d in DATES:
        ax.scatter(DAY0[d], DAY1[d] - DAY0[d], s=11, color=YC[int(d[:4])], edgecolor="white", lw=0.3)
    ax.axhline(0, color=F.FAINT, lw=0.5)
    ax.set_xlabel("Menu's day reading (deg/s)")
    ax.set_ylabel("True center minus\nmenu (deg/s)")
    ax.set_title("Days lifted most: Oct 2024, Oct-Nov 2026", fontsize=6, loc="left")
    # b: mid-day changes
    yb = y + 2.65
    F.letter(fig, 0.4, yb, "b", "On five days the floor changed speed during the day: on 8/12/2026 it jumped from 2.3 to 3.4 "
                                "deg/s at about 2 pm, and late on 3/13/2026 it nearly stalled", width=7.6)
    S1 = SESS.copy()
    days = [("2026-08-12", "Aug 12, 2026 (1629, 1633, 1634: young Hom)"), ("2026-04-10", "Apr 10, 2026 (522, 531, 576)"),
            ("2026-03-13", "Mar 13-14, 2026 (525, 526, 528)"), ("2024-03-31", "Mar 31, 2024 (417, 813)")]
    for k, (d, title) in enumerate(days):
        r, c = divmod(k, 2)
        ax = F.axes_in(fig, 0.75 + c * 3.65, yb + 0.35 + r * 1.75, 3.15, 1.2)
        dset = [d] if d != "2026-03-13" else ["2026-03-13", "2026-03-14"]
        off = 0.0
        for j, dd in enumerate(dset):
            g = S1[S1.date == dd].sort_values("start_h")
            xh = g.start_h + 5 / 60 + off
            sz = 4 + 22 * np.clip(g.n1, 0, 60) / 60
            ok = g.n1 >= 3
            ax.scatter(xh[ok], g.own1[ok], s=sz[ok], color=RC["recentered"], alpha=0.8, lw=0, zorder=3)
            ax.scatter(xh[~ok], np.full((~ok).sum(), 0.6), s=8, marker="v", color=F.ZONE, lw=0, zorder=3)
            ax.plot(xh, g.local1, color=RC["refined"], lw=1.0, zorder=4)
            ax.plot([xh.min(), xh.max()], [DAY1[dd]] * 2, color=F.INK, lw=0.8, ls="--", zorder=2)
            if len(dset) > 1:
                ax.text(xh.mean(), 5.6, dd[5:].replace("-", "/"), fontsize=5.4, ha="center", color=F.SOFT)
                off += 8.0
        ax.set_ylim(0, 6)
        ax.set_title(title, fontsize=6.2, loc="left")
        ax.set_ylabel("Reading (deg/s)")
        if len(dset) > 1:
            ax.set_xticks([])
            ax.set_xlabel("Clock time, two days")
        else:
            ax.set_xlabel("Clock time (h)")
    hs = [Line2D([], [], ls="", marker="o", ms=4, mfc=RC["recentered"], mec="none", label="one session's own reading (size = readings)"),
          Line2D([], [], color=RC["refined"], lw=1.0, label="half-hour reading"),
          Line2D([], [], color=F.INK, lw=0.8, ls="--", label="one number for the day"),
          Line2D([], [], ls="", marker="v", ms=4, mfc=F.ZONE, mec="none", label="no readings (floor below 1.5 deg/s?)")]
    W, H = fig.get_size_inches()
    fig.legend(handles=hs, frameon=False, fontsize=5.6, loc="upper left", ncol=2, bbox_to_anchor=(0.75 / W, 1 - (yb + 3.7) / H))
    U = SESS[SESS.use]
    dl = (U.local1 - U.day1).abs()
    F.put(fig, 0.75, yb + 4.15,
          "Readings about the floor's true center. Half-hour reading: the median of every reading within 30 min of the "
          "session, or of the 15 readings nearest in time when there are fewer. It differs from the day's single number by a median %.2f deg/s per session; "
          "%d of %d sessions differ by more than 0.5. The steps hit the same clock time in every mouse, so they are the "
          "floor, not the mice. Late on 3/13/2026 five sessions gave no readings at all and their mice turned at about "
          "1 deg/s (peak of their 1-s angle speeds), below the rides' 1.5 deg/s floor; the menu gave them the day's 3.2."
          % (dl.median(), (dl > 0.5).sum(), len(U)), 7.0, size=6.3, color=F.SOFT)
    F.save(fig, OUT, "06_weak_spots")


# ============================================================================ page 7: what it means for the menu
def page_menu_effect():
    fig, y = F.page("Read more finely, the floor speeds shift but no story changes; three borderline headlines slip "
                    "past P 0.05", "STAGE SPEED CHECK · 6 · WHAT IT MEANS FOR THE MENU", number=7)
    y += 0.3
    A_ = CQ["ALTS"]
    om0, om1 = A_["menu"]["OM"], A_["refined"]["OM"]
    nb = sum(1 for m in MLIST if A_["menu"]["BAND"][m] != A_["refined"]["BAND"][m])
    dd = np.array([om1[m] - om0[m] for m in MLIST])
    yh = [m for m in MLIST if F.geno(m) == "Hom" and F.young(m)]
    oh = [m for m in MLIST if F.geno(m) == "Hom" and not F.young(m)]
    F.letter(fig, 0.4, y, "a", "Re-read about the true center and within the half hour, mice move by a median %+.2f deg/s and "
                               "%d change band; young Hom (%.1f-%.1f) still all ran slower than every old Hom (%.1f-%.1f)"
             % (np.median(dd), nb, min(om1[m] for m in yh), max(om1[m] for m in yh), min(om1[m] for m in oh),
                max(om1[m] for m in oh)), width=7.6)
    ax = F.axes_in(fig, 0.75, y + 0.3, 1.95, 1.95)
    for m in MLIST:
        F.scatter_mouse(ax, om0[m], om1[m], m, size=16)
    ax.plot([2, 6.5], [2, 6.5], color=F.FAINT, lw=0.6, ls="--")
    for v in (4.0, 4.8):
        ax.axvline(v, color=F.GRID, lw=0.6)
        ax.axhline(v, color=F.GRID, lw=0.6)
    ax.set_xlim(2.3, 6.4)
    ax.set_ylim(2.3, 6.4)
    ax.set_aspect("equal")
    ax.set_xlabel("Mouse's floor speed, menu (deg/s)")
    ax.set_ylabel("Refined reading (deg/s)")
    ax.text(6.35, 4.02, "4.0", fontsize=5, color=F.SOFT, ha="right", va="bottom")
    ax.text(6.35, 4.82, "4.8 (band cuts)", fontsize=5, color=F.SOFT, ha="right", va="bottom")
    F.legend_mice(fig, 3.2, y + 0.4, extra=True, speed=False)
    ch = [m for m in MLIST if A_["menu"]["BAND"][m] != A_["refined"]["BAND"][m]]
    F.put(fig, 3.2, y + 0.75,
          "Each mouse's speed is again the median of its sessions, now with each session's half-hour reading about that "
          "day's true center. The one speed everything is moved to becomes %.2f deg/s (menu %.2f). Band changes (medium to "
          "fast): %s, the Jul and Oct 2024 cohorts. Young Hom %.1f-%.1f deg/s, all slow; old Hom %.1f-%.1f: Angelina's "
          "point stands under every reading on this page." % (A_["refined"]["REF"], A_["menu"]["REF"], ", ".join(ch),
                                                               min(om1[m] for m in yh), max(om1[m] for m in yh),
                                                               min(om1[m] for m in oh), max(om1[m] for m in oh)),
          4.4, size=6.3, color=F.SOFT)
    # b: the headline table
    yb = y + 3.0
    T = pd.DataFrame({k: A_[k]["res"].p.values for k in A_})
    nsig0 = int((T["menu"] < 0.05).sum())
    keep = int(((T["menu"] < 0.05) & (T["refined"] < 0.05)).sum())
    slip = T[(T["menu"] < 0.05) & (T["refined"] >= 0.05)]
    gain = T[(T["menu"] >= 0.05) & (T["refined"] < 0.05)]
    F.letter(fig, 0.4, yb, "b", "%d of the menu's %d headlines below P 0.05 stay there with the refined reading; the %d that "
                                "slip were borderline (P %.3f-%.3f to %.3f-%.3f), and %d borderline one crosses the other way"
             % (keep, nsig0, len(slip), slip.menu.min(), slip.menu.max(), slip.refined.min(), slip.refined.max(), len(gain)),
             width=7.6)
    cols = [("menu", "menu"), ("recentered", "true\ncenter"), ("halfhour", "half-\nhour"), ("refined", "refined\n(both)"),
            ("lenient", "lenient\nrules"), ("win3", "3-s\nwindows"), ("sd015", "steadier"), ("phase", "grid\nshift"),
            ("peak", "1-s\npeak"), ("boot", "redraws\nP < 0.05")]
    ax = F.axes_in(fig, 0.5, yb + 0.22, 7.5, 4.95)
    ax.axis("off")
    cx = [0, 0.33] + [0.33 + 0.0668 * k for k in range(1, 10)]
    ax.text(0, 1, "Headline (story)", fontsize=5.8, weight="bold", va="bottom", transform=ax.transAxes)
    for k, (c, lab) in enumerate(cols):
        ax.text(cx[k + 1], 1, lab, fontsize=5.5, weight="bold", va="bottom", transform=ax.transAxes,
                color=RC.get(c, F.INK))
    boot = 100 * (CQ["BOOTP"] < 0.05).mean(axis=0)
    nrow = len(T)
    rh = 0.96 / nrow
    story_prev = None
    for i, (h, row) in enumerate(zip(CQ["HEAD"], T.itertuples())):
        yy = 0.985 - (i + 1) * rh
        if h[0] != story_prev:
            ax.plot([0, 1], [yy + rh * 0.92, yy + rh * 0.92], color=F.GRID, lw=0.5, transform=ax.transAxes)
            story_prev = h[0]
        ax.text(0, yy, "%s (%s)" % (h[3], h[0]), fontsize=5.6, va="bottom", transform=ax.transAxes)
        for k, (c, _l) in enumerate(cols):
            if c == "boot":
                txt = "n/a" if h[1] in ("MM", "CIRC") else "%.0f%%" % boot[i]
                col = F.INK if (h[1] not in ("MM", "CIRC") and boot[i] >= 50) else F.FAINT
            else:
                p = getattr(row, c)
                txt = pcell(p)
                col = F.INK if (np.isfinite(p) and p < 0.05) else F.FAINT
            wt = "bold" if (c not in ("menu", "boot") and h[1] != "" and np.isfinite(T.loc[i, "menu"]) and
                            c != "boot" and ((T.loc[i, "menu"] < 0.05) != (getattr(row, c) < 0.05))) else "normal"
            ax.text(cx[k + 1], yy, txt, fontsize=5.4, va="bottom", color=col, weight=wt, transform=ax.transAxes)
    F.put(fig, 0.5, yb + 5.27,
          "Every column re-runs the menu's one-speed tests with a different floor reading: slopes re-fitted, bands re-cut "
          "at 4.0 / 4.8 deg/s, and entrances per turn and walking-on-the-floor measures rebuilt from the tracks with that "
          "reading. Bold: crosses P 0.05 against the menu. Gray: P ≥ 0.05. Redraws: share of 200 redraws of every day's "
          "reading (mice resampled within the day) that keep P < 0.05 (not run for the mixed models and directions). "
          "The headlines are the speed supplement's page 5.", 7.5, size=6.0, color=F.SOFT)
    F.save(fig, OUT, "07_what_it_means")


# ============================================================================ page 8: outlier breakdown (who)
def zfmt(r_outliers):
    """'417 (Hom, z +11.0), 827 (Hom, z +4.9)' -> '417 Hom +11.0 · 827 Hom +4.9'."""
    out = []
    for tok in r_outliers.split("), "):
        tok = tok.strip().rstrip(")")
        if not tok:
            continue
        m, rest = tok.split(" (")
        g, z = rest.split(", z ")
        out.append("%s\u00a0%s\u00a0%s" % (m, g, z))
    return " · ".join(out)


def page_outliers():
    fig, y = F.page("Outlier breakdown: a few old Hom carry the raw Hom x age result and two Hom habituation results; the Het "
                    "where-they-wait results stand without their outliers", "STAGE SPEED CHECK · 7 · OUTLIERS", number=8)
    y += 0.3
    SU = X["SUMM"]
    FR = X["FREQ"].set_index("mouse")
    F.letter(fig, 0.4, y, "a", "Mouse 417, an old Hom, is flagged most (%d times); without the outliers the raw Hom x age "
                               "interaction and two of Hom's three habituation results go, and Hom's entrance deficit sharpens"
             % int(FR.loc["417", "outlier"]), width=7.6)
    rows = SU[(SU.outliers != "")].copy()
    ax = F.axes_in(fig, 0.5, y + 0.25, 7.5, 4.0)
    ax.axis("off")
    W_, H_ = 7.5, 4.0
    hx = [0, 0.29, 0.375, 0.80, 0.905]
    for j, h in enumerate(["Headline", "Reading", "Outliers (mouse, genotype, robust z)", "P, all mice", "P without them"]):
        ax.text(hx[j], 1, h, fontsize=5.9, weight="bold", va="bottom", transform=ax.transAxes, color=F.SOFT)
    yy = 0.975
    prev = None
    for r in rows.itertuples():
        txt = F.wrap(zfmt(r.outliers), (hx[3] - hx[2]) * W_ - 0.1, 5.5)
        nl = txt.count("\n") + 1
        if r.label != prev and prev is not None:
            ax.plot([0, 1], [yy + 0.025 / H_, yy + 0.025 / H_], color=F.GRID, lw=0.5, transform=ax.transAxes)
        cells = [r.label if r.label != prev else "", r.reading, txt, pcell(r.p_all), pcell(r.p_no_outliers)]
        prev = r.label
        for j, c in enumerate(cells):
            col = F.INK
            if j in (3, 4):
                p = r.p_all if j == 3 else r.p_no_outliers
                col = F.INK if p < 0.05 else F.FAINT
            wt = "bold" if (j == 4 and ((r.p_all < 0.05) != (r.p_no_outliers < 0.05))) else "normal"
            ax.text(hx[j], yy, c, fontsize=5.5, va="top", transform=ax.transAxes, color=col, weight=wt, linespacing=1.2)
        yy -= (0.155 + 0.095 * (nl - 1)) / H_
    F.put(fig, 0.5, y + 3.95,
          "Outlier: more than 3.5 robust s.d. (1.4826 x MAD) from its genotype's median on that measure (raw values for raw, "
          "values at one floor speed for one speed), in the groups the headline compares; all of a row's outliers dropped "
          "together. Bold: crosses P 0.05. Headlines with no outliers either way are left out (13 of 25). Tests as on page 10.",
          7.5, size=6.0, color=F.SOFT)
    # b: who keeps turning up
    yb = y + 4.75
    F.letter(fig, 0.4, yb, "b", "The mice that keep turning up are mostly old 2024 Hom; they stay outliers with the refined floor "
                                "reading, so it is the mice, not the floor speed, that makes them stand out", width=7.6)
    fr = X["FREQ"][X["FREQ"].total >= 1].copy()
    ax = F.axes_in(fig, 1.3, yb + 0.35, 3.0, 3.3)
    for i, r in enumerate(fr.itertuples()):
        col = F.GCOL[r.geno]
        ax.barh(i, r.outlier, color=col, height=0.65)
        ax.barh(i, r._6, left=r.outlier, color=col, alpha=0.35, height=0.65, hatch="////", edgecolor="white", lw=0)
        ax.text(-0.3, i, "%s  %s %s %d" % (r.mouse, r.geno, r.age, r.year), fontsize=5.8, ha="right", va="center")
    ax.set_ylim(len(fr) - 0.4, -0.6)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Headline x reading pairs (of 50)")
    ax.legend(handles=[Rectangle((0, 0), 1, 1, color=F.FAINT, label="flagged as an outlier"),
                       Rectangle((0, 0), 1, 1, color=F.FAINT, alpha=0.35, hatch="////", label="the mouse whose loss flips P most")],
              frameon=False, fontsize=5.6, loc="lower right")
    shaky = X["SHAKY"].set_index("mouse")
    notes = []
    for m in fr.mouse:
        if m in shaky.index:
            notes.append("%s: %s" % (m, shaky.loc[m, "why"]))
    F.put(fig, 4.9, yb + 0.4,
          "Counted over 25 per-mouse headlines, raw and at one speed (50 pairs). Outlier flags: 417 on day-2 shocks (z up to "
          "+11 raw), habituation and improvement; 827 and 418 on day-2 shocks and habituation; 413 on day-1 shocks and "
          "improvement; 459 on day-1 walking. 'Flips P most': the one mouse whose removal moves a P below 0.05 the most "
          "toward 0.05 or past it (page 9).\n\nFloor notes for these mice (page 6): " + "; ".join(notes) +
          ". Under the refined reading 417, 827 and 1634 are still the day-2 shock outliers (page 10, table c).",
          3.0, size=6.2, color=F.INK)
    F.save(fig, OUT, "08_outliers")


# ============================================================================ page 9: leave one mouse out
def page_dropone():
    fig, y = F.page("Leave any one mouse out: half the headlines below P 0.05 survive every single loss; the others hang "
                    "on one or a few mice", "STAGE SPEED CHECK · 8 · LEAVE ONE MOUSE OUT", number=9)
    y += 0.3
    J = X["JACK"]
    heads = [h for h in CQ["HEAD"] if h[1] not in ("MM", "CIRC")]
    hold = [h[3] for h in heads if J[(h[3], "one speed")]["p"] < 0.05 and
            all(p < 0.05 for p in J[(h[3], "one speed")]["drop"].values() if np.isfinite(p))]
    nsig = sum(1 for h in heads if J[(h[3], "one speed")]["p"] < 0.05)
    F.letter(fig, 0.4, y, "a", "At one floor speed %d of the %d headlines below P 0.05 stay there whichever mouse goes, among "
                               "them Hom reaching criterion sooner than WT, Hom improving less (shocks) and every Het "
                               "where-they-wait result" % (len(hold), nsig), width=7.6)
    rowh = 0.27
    top = y + 0.55
    for k, rd in enumerate(("one speed", "raw")):
        x0 = 2.55 + k * 2.75
        ax = F.axes_in(fig, x0, top, 1.95, rowh * len(heads))
        for i, h in enumerate(heads):
            d = J[(h[3], rd)]
            ps = np.array([p for p in d["drop"].values() if np.isfinite(p)])
            ax.scatter(np.clip(ps, 1e-5, 1), i + (np.random.RandomState(i).rand(ps.size) - 0.5) * 0.45, s=3.5,
                       color=F.FAINT, lw=0)
            p0 = d["p"]
            ax.scatter([max(p0, 1e-5)], [i], s=20, marker="D", color=F.KICK if p0 < 0.05 else F.SOFT, zorder=3, lw=0)
            sig = p0 < 0.05
            flips = [m for m, p in d["drop"].items() if np.isfinite(p) and (p >= 0.05) == sig]
            W, H = fig.get_size_inches()
            yy = 1 - (top + (i + 0.5) * rowh) / H
            if sig and flips:
                m_ = max(flips, key=lambda m: d["drop"][m])
                lab = ("%d mice, most %s" % (len(flips), m_)) if len(flips) > 1 else ("only %s" % m_)
                fig.text((x0 + 2.0) / W, yy, lab, fontsize=5.2, va="center", color=F.ZONE)
            elif sig:
                fig.text((x0 + 2.0) / W, yy, "holds", fontsize=5.2, va="center", color=F.KICK)
            elif flips:
                fig.text((x0 + 2.0) / W, yy, "%d mice pull it under" % len(flips), fontsize=5.0, va="center", color=F.SOFT)
            if k == 0:
                fig.text(2.45 / W, yy, "%s (%s)" % (h[3], h[0]), fontsize=5.8, va="center", ha="right")
        ax.axvline(0.05, color=F.ZONE, lw=0.6, ls="--")
        ax.set_xscale("log")
        ax.set_xlim(1e-5, 1)
        ax.set_xticks([1e-4, 1e-3, 0.01, 0.05, 1])
        ax.set_xticklabels(["0.0001", "0.001", "0.01", "0.05", "1"], fontsize=5.4)
        ax.minorticks_off()
        ax.set_ylim(len(heads) - 0.5, -0.5)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        for i in range(len(heads)):
            if i and heads[i][0] != heads[i - 1][0]:
                ax.axhline(i - 0.5, color=F.GRID, lw=0.5)
        ax.set_title("At one floor speed" if k == 0 else "Raw", fontsize=6.8, loc="left", color=F.KICK if k == 0 else F.INK,
                     weight="bold")
        ax.set_xlabel("P with one mouse left out")
    F.put(fig, 0.5, top + rowh * len(heads) + 0.55,
          "Gray dots: P with each mouse of the compared groups left out in turn (Hom only for the young-vs-old rows); diamond: "
          "P with every mouse, blue when below 0.05. Right of each strip: 'holds' when no single mouse lifts P to 0.05 or "
          "above; otherwise how many do and the one that lifts it most (red); for results above 0.05, how many single losses "
          "would pull P under it. Slope re-fitted each time, as in the menu. Borderline results (P 0.03-0.05) fall to one "
          "mouse almost by definition; read them as leads.", 7.5, size=6.1, color=F.SOFT)
    F.save(fig, OUT, "09_leave_one_out")


# ============================================================================ page 10: the checks table three ways
def page_tables():
    fig, y = F.page("The menu's check table three ways: at one floor speed, raw, and at one speed with the refined reading",
                    "STAGE SPEED CHECK · 9 · THE CHECK TABLE", number=10)
    y += 0.3
    drops = X["DROPS"]
    labs = {"all mice": "all mice", "no outliers*": "no\noutliers*", "no 461/462/457": "no 461/\n462/457",
            "no injected ≤ 7 d": "no injected\n≤ 7 d", "no injected": "no\ninjected", "2024 only": "2024\nonly",
            "2026 only": "2026\nonly"}
    Ta, Tc = X["TABLES"]["one speed"], X["TABLES"]["one speed, refined reading"]
    diff = []
    for i in range(len(Ta)):
        for dname in drops:
            a, c = Ta.loc[i, dname], Tc.loc[i, dname]
            if np.isfinite(a) and np.isfinite(c) and (a < 0.05) != (c < 0.05):
                diff.append("%s, %s" % (Ta.loc[i, "headline"].split(" (")[0], dname))
    blocks = [("one speed", "a", "At one floor speed (the menu's reading): improvement and where-they-wait hold in most checks, "
                                 "the year halves are too small to carry them, and the Hom age effect never appears", F.KICK),
              ("raw", "b", "Raw, before any speed adjustment: Hom's day-1 shock gap and the Hom age effect look real; both "
                           "follow the floor speed (speed supplement, pages 4-5)", F.INK),
              ("one speed, refined reading", "c", "At one floor speed with the refined floor reading: the same cells clear "
                                                  "P 0.05 as in (a), except %d of %d (%s)" % (
                                                      len(diff), int(np.isfinite(Ta[drops].values).sum()), "; ".join(diff)),
               RC["refined"])]
    yy0 = y
    for name, let, head, col in blocks:
        T = X["TABLES"][name]
        F.letter(fig, 0.4, yy0, let, head, width=7.6)
        ax = F.axes_in(fig, 0.5, yy0 + 0.12, 7.5, 1.95)
        ax.axis("off")
        cx = [0, 0.36] + [0.36 + 0.0915 * k for k in range(1, 7)]
        ax.text(0, 1, "Headline", fontsize=6.0, weight="bold", va="top", transform=ax.transAxes)
        for k, dname in enumerate(drops):
            ax.text(cx[k + 1], 1, labs[dname], fontsize=5.9, weight="bold", va="top", transform=ax.transAxes, color=col,
                    linespacing=1.1)
        for i, r in enumerate(T.itertuples()):
            yyy = 0.80 - i * 0.087
            ax.text(0, yyy, r.headline, fontsize=6.0, va="top", transform=ax.transAxes)
            for k, dname in enumerate(drops):
                p = T.loc[i, dname]
                ax.text(cx[k + 1], yyy, pcell(p), fontsize=6.0, va="top", transform=ax.transAxes,
                        color=F.INK if (np.isfinite(p) and p < 0.05) else F.FAINT)
        od = "; ".join("%s: %s" % (r.headline.split(" (")[0], r.outliers_dropped) for r in T.itertuples() if r.outliers_dropped)
        F.put(fig, 0.5, yy0 + 2.07, "*Dropped as outliers. " + (od if od else "none"), 7.5, size=5.5, color=F.SOFT)
        yy0 += 2.75
    F.put(fig, 0.5, yy0 - 0.2,
          "Tests: raw = the menu's raw tests (Mann-Whitney / Welch / Student, smallest P; log-rank family for the criterion). "
          "One speed = values moved to one floor speed along the slope shared by the genotypes, re-fitted on the mice kept; "
          "the same tests on the moved values plus van Elteren inside the speed bands (Cox with speed and band-stratified "
          "log-rank for the criterion), so 'all mice' equals the menu's headline P. Page 11 of the menu ran its drop columns "
          "without the band test, so a few one-speed cells there differ slightly. Outliers: > 3.5 robust s.d. from the "
          "genotype median on the values the column tests. Gray: P ≥ 0.05. n/a: no young Hom in 2024 or among the "
          "uninjected, or no outlier rule for a time-to-criterion measure.", 7.5, size=5.9, color=F.SOFT)
    F.save(fig, OUT, "10_check_table")


# ============================================================================ page 1: the menu
def page_front():
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(8.5, 11))
    A_ = CQ["ALTS"]
    T = pd.DataFrame({k: A_[k]["res"].p.values for k in A_})
    nsig0 = int((T["menu"] < 0.05).sum())
    keep = int(((T["menu"] < 0.05) & (T["refined"] < 0.05)).sum())
    P = O["PAIR"]
    m0 = O["MD"][O["MD"].reading == "menu"]
    pr = []
    for _d, g in m0.groupby("date"):
        v = g.own.values
        pr += [(v[i], v[j]) for i in range(len(v)) for j in range(i + 1, len(v))]
    RPAIR = float(np.corrcoef(np.array(pr).T)[0, 1])
    J = X["JACK"]
    hh = [h for h in CQ["HEAD"] if h[1] not in ("MM", "CIRC")]
    NSIG1 = sum(1 for h in hh if J[(h[3], "one speed")]["p"] < 0.05)
    NHOLD = sum(1 for h in hh if J[(h[3], "one speed")]["p"] < 0.05 and
                all(p < 0.05 for p in J[(h[3], "one speed")]["drop"].values() if np.isfinite(p)))
    meds = [np.median(np.abs((O["DAYV"][n].reindex(DAY0.index) - DAY0).dropna()))
            for n in ("win3", "win6", "win8", "sd015", "sd040", "dr02", "dr08", "lo10", "hi12", "r8", "r20", "phase", "nolost",
                      "lenient")]
    SHIFT = float(np.median([A_["refined"]["OM"][m] - A_["menu"]["OM"][m] for m in MLIST]))
    F.put(fig, 0.7, 0.8, "BARRY LAB · KCNT1 ACTIVE AVOIDANCE · STAGE SPEED CHECK, 2026-11-24", 7.2, size=7.2, color=F.KICK,
          weight="bold")
    F.put(fig, 0.7, 1.05, "How fast did the stage turn? A sanity check", 7.2, size=17, weight="bold")
    F.put(fig, 0.7, 1.5, "A supplement to the KCNT1 AA story menu and its speed supplement: how the floor's turning speed is "
                         "read from the mice, how far that reading can be trusted, what its weak spots do to the headlines, an "
                         "outlier breakdown, and the menu's check table at one floor speed and raw.", 7.2, size=8,
          color=F.SOFT)
    F.put(fig, 0.72, 2.3, "The short version", 7.2, size=7.5, weight="bold")
    F.put(fig, 0.72, 2.55,
          "The tracker never logs the floor's speed, only the mouse. A mouse that sits still is carried around at the floor's "
          "speed, so every 4-s stretch at a steady radius and angle speed is one reading; a day's speed is the median of its "
          "readings (12,188 in all, 55-1,033 a day). The reading holds up. On the one day with a direct measurement it read "
          "%.2f against %.2f deg/s, and the gap is the mouse creeping forward; without the creep it reads %.2f. When the motor "
          "log read 'off', it read 0.0. Changing a ride rule moves a day by a median of %.2f-%.2f deg/s; resampling the "
          "mice, by ±%.2f; two mice on the same day agree (r %.2f); the mouse's genotype does not change it. Two things one number per "
          "day misses: the floor turns about a point %s off the tracker's center, which reads some days 0.2-0.5 deg/s "
          "low, and on five days the floor changed speed mid-day (8/12/2026: 2.3 to 3.4 deg/s at about 2 pm). Re-reading every "
          "session about the true center within its half hour moves mice by a median %.2f deg/s and changes no story: %d of "
          "%d headlines below P 0.05 stay there, and the %d that slip were borderline. Young Hom ran slower than every old "
          "Hom under every reading, so Angelina's point stands. Outliers: old Hom 417 is flagged most; the raw age effect "
          "and Hom's habituation results lean on it and on 827, while Hom reaching criterion sooner, Hom improving less "
          "(shocks) and every Het where-they-wait result survive the loss of any one mouse."
          % (np.median(P["rides"]), P["slope"], np.median(P["rides"] - P["creep"]), min(meds), max(meds),
             np.median([O["BOOT"]["menu"][d][1] - O["BOOT"]["menu"][d][0] for d in DATES]) / 2, RPAIR, OFFTXT, SHIFT,
             keep, nsig0, nsig0 - keep),
          7.0, size=7.3)
    F.put(fig, 0.72, 4.3, "The pages", 7.2, size=7.5, weight="bold")
    rows = [("2", "How it is read", "One ride step by step; a day's readings; from days to a mouse.", "17-s ride = 14 readings, 5.29 deg/s"),
            ("3", "Known answers", "The 10/7/2025 floor-frame day; sessions where the motor log changed.",
             "direct %.2f; rides minus creep %.2f; motor off reads 0.0" % (P["slope"], np.median(P["rides"] - P["creep"]))),
            ("4", "Robust to the rules", "Fourteen rule changes; two methods without rules.", "median shift %.2f-%.2f deg/s a day" % (min(meds), max(meds))),
            ("5", "Precise and unbiased", "Resampled days; pairs of mice; reading by genotype.", "no genotype effect on the reading"),
            ("6", "Weak spots", "The off-center turn; floor speed changing mid-day.", "8/12/2026: 2.3 to 3.4 deg/s at 2 pm"),
            ("7", "What it means", "Every headline under nine readings and 200 redraws.", "%d of %d stay below P 0.05" % (keep, nsig0)),
            ("8", "Outliers", "The outliers of every headline, raw and at one speed; the mice that keep turning up.",
             "417 (old Hom) flagged most"),
            ("9", "Leave one mouse out", "Every headline's P with each mouse left out in turn.", "%d of %d hold whichever mouse goes" % (
                NHOLD, NSIG1)),
            ("10", "The check table", "Page 11 of the menu at one speed, raw, and with the refined reading.", "same columns, three readings")]
    ax = F.axes_in(fig, 0.7, 4.55, 7.3, 3.9)
    ax.axis("off")
    hx = [0, 0.05, 0.25, 0.66]
    for j, h in enumerate(["Page", "Story", "What it shows", "Best number"]):
        ax.text(hx[j], 1, h, fontsize=6.6, weight="bold", va="top", color=F.SOFT, transform=ax.transAxes)
    yy = 0.91
    for r in rows:
        cells = [r[0], F.wrap(r[1], 1.3, 6.8), F.wrap(r[2], 2.9, 6.8), F.wrap(r[3], 2.35, 6.8)]
        nl = max(c.count("\n") + 1 for c in cells)
        for j, c in enumerate(cells):
            ax.text(hx[j], yy, c, fontsize=6.8, va="top", weight="bold" if j == 1 else "normal", transform=ax.transAxes)
        yy -= 0.04 * nl + 0.045
        ax.plot([0, 1], [yy + 0.022, yy + 0.022], color=F.GRID, lw=0.6, transform=ax.transAxes)
    F.put(fig, 0.72, 8.75,
          "What to do next time: write the floor speed on the run sheet every day (time one turn of a mark on the floor "
          "with a stopwatch before the first mouse and after the last), keep the floor-frame file switched on, and run the "
          "groups of each comparison in the same weeks. For this data set the menu's day readings stand; the refined "
          "reading is the better default for any re-run. Tables: tables/ (every reading per day and session, headline P "
          "values under each reading, outliers, drop-one P values, the three check tables). * P < 0.05, ** P < 0.01, "
          "*** P < 0.001.", 7.2, size=6.6, color=F.SOFT)
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, F.FOOT, fontsize=6.5, color=F.FAINT, ha="left", va="bottom")
    fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, "1", fontsize=6.5, color=F.FAINT, ha="right", va="bottom")
    F.save(fig, OUT, "01_menu")


# ============================================================================ package
def package():
    os.makedirs(DEST, exist_ok=True)
    for sub in ("pages", "tables", "code"):
        p = os.path.join(DEST, sub)
        if os.path.isdir(p):
            shutil.rmtree(p)
        os.makedirs(p)
    pdfs = sorted(glob.glob(os.path.join(OUT, "*.pdf")))
    for f in pdfs + sorted(glob.glob(os.path.join(OUT, "*.png"))):
        shutil.copy2(f, os.path.join(DEST, "pages"))
    doc = pymupdf.open()
    for f in pdfs:
        doc.insert_pdf(pymupdf.open(f))
    doc.save(os.path.join(DEST, "KCNT1_AA_Stage_Speed_Check_112426.pdf"))
    tab = os.path.join(DEST, "tables")
    days = pd.DataFrame(dict(date=DATES, menu=[DAY0[d] for d in DATES], true_center=[DAY1[d] for d in DATES],
                             rigid_fit=[O["RIGID"][d] for d in DATES], peak_1s=[O["MODE0"][d] for d in DATES],
                             peak_1s_true_center=[O["MODE1"][d] for d in DATES],
                             center_x_cm=[O["CENTER"][d][0] for d in DATES], center_y_cm=[O["CENTER"][d][1] for d in DATES],
                             n_readings=[int((W0.date == d).sum()) for d in DATES],
                             ci95_lo=[O["BOOT"]["menu"][d][0] for d in DATES], ci95_hi=[O["BOOT"]["menu"][d][1] for d in DATES],
                             **{"rule_" + n: [O["DAYV"][n].get(d, np.nan) for d in DATES] for n in O["VARIANTS"]}))
    days.to_csv(os.path.join(tab, "floor_speed_by_day.csv"), index=False)
    s = SESS.rename(columns={"n0": "n_readings", "own0": "own_reading", "day0": "day_reading_menu", "n1": "n_readings_true_center",
                             "own1": "own_reading_true_center", "day1": "day_reading_true_center",
                             "local0": "half_hour_reading", "local1": "half_hour_reading_true_center"})
    s.to_csv(os.path.join(tab, "floor_speed_by_session.csv"), index=False)
    A_ = CQ["ALTS"]
    pm = pd.DataFrame({k: pd.Series(A_[k]["OM"]) for k in ("menu", "recentered", "halfhour", "refined", "lenient", "peak")})
    pm.index.name = "mouse"
    pm.insert(0, "genotype", [F.geno(m) for m in pm.index])
    pm.insert(1, "age_group", [F.MICE[m]["age_group"] for m in pm.index])
    pm.to_csv(os.path.join(tab, "floor_speed_by_mouse.csv"))
    T = pd.DataFrame({k: A_[k]["res"].p.values for k in A_ if k != "menu_full"})
    T.insert(0, "headline", [h[3] for h in CQ["HEAD"]])
    T.insert(0, "story", [h[0] for h in CQ["HEAD"]])
    T["redraws_share_P_below_0.05"] = (CQ["BOOTP"] < 0.05).mean(axis=0)
    T.to_csv(os.path.join(tab, "headlines_under_each_reading.csv"), index=False)
    X["SUMM"].to_csv(os.path.join(tab, "outliers_by_headline.csv"), index=False)
    X["OUTL"].to_csv(os.path.join(tab, "outlier_mice.csv"), index=False)
    jr = []
    for (lab, rd), d in X["JACK"].items():
        for m, p in d["drop"].items():
            jr.append(dict(headline=lab, reading=rd, mouse_left_out=m, p=p, p_all_mice=d["p"]))
    pd.DataFrame(jr).to_csv(os.path.join(tab, "drop_one_mouse_P.csv"), index=False)
    with pd.ExcelWriter(os.path.join(tab, "check_table_three_ways.xlsx")) as xw:
        for name, t in X["TABLES"].items():
            t.to_excel(xw, sheet_name=name.replace(",", "")[:31], index=False)
    X["FREQ"].to_csv(os.path.join(tab, "mice_flagged_most.csv"), index=False)
    for f in ("c1_floor_cache.py", "floorlib.py", "c2_floor_check.py", "c3_consequences.py", "c4_outliers.py", "s2_floor_pages.py"):
        shutil.copy2(os.path.join(F.HERE, f), os.path.join(DEST, "code"))
    print("packaged to", DEST)


if __name__ == "__main__":
    import sys
    which = sys.argv[1:] or ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "pkg"]
    fns = {"1": page_front, "2": page_method, "3": page_known, "4": page_rules, "5": page_precise, "6": page_misses,
           "7": page_menu_effect, "8": page_outliers, "9": page_dropone, "10": page_tables, "pkg": package}
    for w in which:
        fns[w]()
        print("done", w)
