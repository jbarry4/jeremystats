"""The frozen dentate-spike pilot dataset (2026-11-16) and the depth
normalization. READ ONLY: nothing here writes, and nothing here talks to
Jarvis. See README.md for every field.

    import dsdata
    recs = dsdata.load("v6")          # list of Rec, one per recording (mouse)
    r = dsdata.by_lab(recs)["m60"]
    r.csd_peak                         # events x 64 contacts, CSD at the DS peak
    r.types("bite")                    # 1 = DS1, 2 = DS2 for every event
"""
import os
import pickle

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SPACING_UM = 20.0               # KCNT1: Cambridge H3, 20 um per contact (the PTEN copy kept 50)
MIN_EVENTS = 20                 # a recording under this is left out of every test (m51)
EXCLUDED = {}
NAME_MIN_UM = 25.0              # half a contact: closer than this, the two types' sinks are "at the same place"
SEPARABLE = 0.45                # separation index from which DS1 and DS2 are called separable
PEAK_HALF_MS = 3.0              # "at the DS peak" = the mean over +-3 ms
CLASSIFIERS = ["bite", "bite_top", "bite_bottom", "pca", "pca_top", "pca_bottom", "pca_gap", "pca_gap_top", "pca_gap_bottom",
               "delta", "delta_top", "delta_bottom", "delta_mid", "delta_mid_top", "delta_mid_bottom",
               "pca_gmm_line", "pca_gmm_curve", "opt_line", "opt_curve"]
CONVENTIONAL = CLASSIFIERS[:17]  # the two opt_* were fitted to maximize the separation index


def fill_bad(profile, bad_rows):
    """A depth profile (..., 64) with the bad rows replaced by a straight
    line between their good neighbors. The CSD at a bad contact is not a
    measurement (its voltage was filled in before the CSD was taken)."""
    p = np.array(profile, dtype=float, copy=True)
    bad = sorted(set(int(b) for b in bad_rows if 0 <= int(b) < p.shape[-1]))
    if not bad:
        return p
    good = np.array([i for i in range(p.shape[-1]) if i not in bad])
    flat = p.reshape(-1, p.shape[-1])
    for k in range(flat.shape[0]):
        flat[k, bad] = np.interp(bad, good, flat[k, good])
    return flat.reshape(p.shape)


def _centroid(y, i0, frac=0.5):
    """Sub-contact position of the lobe of y (positive there) around i0:
    the centroid of what stands above `frac` of its height."""
    h = y[i0] * frac
    lo = i0
    while lo - 1 >= 0 and y[lo - 1] > h:
        lo -= 1
    hi = i0
    while hi + 1 < y.size and y[hi + 1] > h:
        hi += 1
    w = y[lo:hi + 1] - h
    w = np.maximum(w, 0.0)
    return float((w * np.arange(lo, hi + 1)).sum() / w.sum()) if w.sum() > 0 else float(i0)


class Rec(object):
    """One recording (one mouse). Rows are 0-based positions down the shank,
    row 0 the top contact; contact number = row + 1; 50 um between rows."""

    def __init__(self, d):
        self.__dict__.update(d)
        self.dur_min = self.dur_s / 60.0
        self.year = int(self.date[:4])
        self.excluded = EXCLUDED.get(self.lab)
        self.ok = self.n >= MIN_EVENTS and not self.excluded
        self.bad_rows = [self.contacts.index(c) for c in self.bad if c in self.contacts]
        w = np.abs(self.t_ms) <= PEAK_HALF_MS
        self.csd_peak = self.csd[:, :, w].mean(axis=2)          # events x 64
        self.lfp_peak = self.lfp[:, :, w].mean(axis=2)          # events x 64 (uV)
        self.mean_csd_peak = fill_bad(self.csd_peak.mean(axis=0), self.bad_rows)
        self.landmarks = self._landmarks(self.mean_csd_peak)
        # Names and DS3, checked again (2026-11-17; see the sanity check in METHODS.md)
        self.ds3_score_jarvis = dict(self.ds3_score)
        self.ds3_gap_um_jarvis = dict(self.ds3_gap_um)
        self.naming, self.ds3w = {}, {}
        if self.landmarks is not None:
            for clf in list(self.labels):
                chk = self._name_check(self.types(clf))
                self.naming[clf] = chk
                if chk["verdict"] == "swapped":
                    self._swap(clf)
                self.ds3w[clf] = self._ds3_widened(self.types(clf))
                self.ds3_gap_um[clf] = self.ds3w[clf].get("gap_um")
        self._set_winner()

    # ------------------------------------------------------------ the winner
    def _si_without(self, t3):
        """Whole-band separation index of DS1 against DS2 among the events
        still DS1 or DS2 in t3 (DS3 = 3 taken out); as the quality check."""
        Wd = getattr(self, "W", None) or {}
        if "both" not in Wd:
            return None
        keep = np.where((t3 == 1) | (t3 == 2))[0]
        W0 = np.asarray(Wd["both"], float)[np.ix_(keep, keep)].copy()
        np.fill_diagonal(W0, 0.0)
        m = t3[keep] == 1
        na, nb = int(m.sum()), int((~m).sum())
        if na < 2 or nb < 2:
            return None
        Wm = W0 @ m
        saa, sab = float(m @ Wm), float((~m) @ Wm)
        sbb = float(W0.sum()) - saa - 2.0 * sab
        return 1.0 - (sab / (na * nb)) / ((saa / (na * (na - 1)) + sbb / (nb * (nb - 1))) / 2.0)

    def _set_winner(self):
        """THE WINNER (asked 2026-11-18: "We had the winner. Keep those winners
        and vary everything else"). The row the round 11 quality check marks
        FINAL OPTIMIZED SEPARATION: of (1) the best eligible room classifier,
        (2) the best conventional classifier on the PCA plane, (3) the
        index-optimized curve, the one whose DS1 and DS2 separate best once
        DS3 is taken out (each type 5 events or more). A tie (within 0.005)
        goes to the lower row. The battery classifies with this one only."""
        self.winner, self.winner_row, self.winner_si = None, None, None
        if self.n < MIN_EVENTS or self.landmarks is None:
            return
        el = lambda k: self.has(k) and self.eligible(k)
        room = [k for k in CLASSIFIERS[:15] if el(k)]
        plane = [k for k in ("pca", "pca_gmm_line", "pca_gmm_curve") if self.has(k)]
        rows = {1: max(room, key=self.si) if room else None,
                2: max([k for k in plane if el(k)] or plane, key=self.si) if plane else None,
                3: "opt_curve" if self.has("opt_curve") else None}
        fin = {}
        for row, k in rows.items():
            if k is None:
                continue
            t = self.types(k)
            s = (self.ds3w.get(k) or {}).get("score")
            m3 = np.zeros(self.n, bool) if s is None else (np.isfinite(np.asarray(s, float)) & (np.abs(np.asarray(s, float)) <= 0.5))
            t3 = np.where(m3, 3, t)
            if min((t3 == 1).sum(), (t3 == 2).sum()) >= 5:
                v = self._si_without(t3)
                if v is not None:
                    fin[row] = v
        if not fin:
            return
        top = max(fin.values())
        row = min(r_ for r_, v in fin.items() if v >= top - 0.005)
        k = rows[row]
        self.winner, self.winner_row, self.winner_si = k, row, fin[row]
        self.labels["winner"] = dict(self.labels[k], eligible=True, winner_of=k)
        self.ds3w["winner"] = self.ds3w.get(k) or {}
        self.naming["winner"] = self.naming.get(k)
        self.ds3_gap_um["winner"] = self.ds3_gap_um.get(k)
        if k in self.ds3_score_jarvis:
            self.ds3_score_jarvis["winner"] = self.ds3_score_jarvis[k]

    # ------------------------------------------------------------ labels
    def has(self, clf):
        return clf in self.labels

    def types(self, clf):
        """1 = DS1, 2 = DS2 for every event, as Jarvis names them (DS1 is the
        type whose mean main sink is the shallower one)."""
        return np.asarray(self.labels[clf]["types"], int)

    def si(self, clf):
        return self.labels[clf]["si"]

    def eligible(self, clf):
        """Each type holds 5% of events or more (and 5 events or more)."""
        return bool(self.labels[clf]["eligible"])

    def separable(self, clf=None):
        clf = clf or self.used
        return bool(clf and self.eligible(clf) and self.si(clf) >= SEPARABLE)

    def ds3(self, clf, cut=0.5, which="widened"):
        """True where the event is DS3 under this classifier (relative sink
        within +-cut), or None when DS3 cannot be scored (DS1's and DS2's
        mean sinks peak at the same contact).
        which="widened" (default since 2026-11-17): outer and middle contacts
        looked for past the analyzed band too (blade_rows, 5 contacts), on
        the far side of the blade's source only; "jarvis": as the room and
        backend/dsmix.relsink did it, inside the analyzed band only."""
        if which == "jarvis":
            s = self.ds3_score_jarvis.get(clf)
        else:
            s = (self.ds3w.get(clf) or {}).get("score")
        if s is None:
            return None
        s = np.asarray(s, float)
        return np.isfinite(s) & (np.abs(s) <= cut)

    def ds3_category(self, clf, cut=0.5, which="widened"):
        """Per event by the score alone, as the paper does it: 1 = sink mostly
        at the outer contact, 2 = mostly at the middle, 3 = shared (DS3),
        0 = unscored (both sinks under the floor). None when not scorable."""
        s = self.ds3_score_jarvis.get(clf) if which == "jarvis" else (self.ds3w.get(clf) or {}).get("score")
        if s is None:
            return None
        s = np.asarray(s, float)
        return np.where(~np.isfinite(s), 0, np.where(s > cut, 1, np.where(s < -cut, 2, 3)))

    def types3(self, clf, cut=0.5):
        """types() with DS3 events set to 3 (unchanged when DS3 cannot be scored)."""
        t = self.types(clf).copy()
        m = self.ds3(clf, cut)
        if m is not None:
            t[m] = 3
        return t

    # ------------------------------------------------------------ names, DS3
    def far_rows(self, blade, widen=5):
        """The good rows of one blade on the far side of its source (the
        molecular layer side), widened past the band by `widen` contacts."""
        k = self.landmarks
        rows = self.good(self.blade_rows(blade, widen))
        if blade == "upper":
            return rows[rows < k["GU"] - 0.5]
        return rows[rows > k["GL"] + 0.5]

    def sink_distance_um(self, profile, blade):
        """Where a mean profile's sink sits in one blade: the centroid of its
        deepest lobe (half height) on the far side of the source, as microns
        from that blade's source. (nan, None) when there is no sink there."""
        k = self.landmarks
        rows = self.far_rows(blade)
        if rows.size < 2:
            return np.nan, None
        p = fill_bad(profile, self.bad_rows)
        y = np.zeros(p.size)
        y[rows] = np.maximum(-p[rows], 0.0)
        i0 = int(rows[int(np.argmax(y[rows]))])
        if y[i0] <= 0:
            return np.nan, None
        c = _centroid(y, i0)
        src = k["GU"] if blade == "upper" else k["GL"]
        return abs(c - src) * SPACING_UM, i0

    def _name_check(self, t):
        """Does the name follow the anatomy? DS1 should be the type whose
        sink sits farther from the cell layer (outer molecular layer).
        diff = DS1's distance minus DS2's, per blade (um)."""
        if not ((t == 1).any() and (t == 2).any()):
            return {"verdict": "one type", "diff": [np.nan, np.nan]}
        mu = {c: self.csd_peak[t == c].mean(axis=0) for c in (1, 2)}
        d = {c: [self.sink_distance_um(mu[c], b)[0] for b in ("upper", "lower")] for c in (1, 2)}
        diff = np.array(d[1]) - np.array(d[2])
        s = float(np.nansum(diff))
        if not np.isfinite(diff).any():
            v = "no sink"
        elif (diff >= NAME_MIN_UM).any() and (diff <= -NAME_MIN_UM).any():
            v = "blades disagree"
        elif s >= NAME_MIN_UM:
            v = "ok"
        elif s <= -NAME_MIN_UM:
            v = "swapped"
        else:
            v = "same place"
        return {"verdict": v, "diff": [float(x) for x in diff], "dist1": d[1], "dist2": d[2]}

    def _swap(self, clf):
        L = self.labels[clf]
        t = np.asarray(L["types"], int)
        L["types_jarvis"] = t.copy()
        L["types"] = np.where(t == 1, 2, np.where(t == 2, 1, t))
        L["n1"], L["n2"] = L.get("n2"), L.get("n1")
        if self.ds3_score_jarvis.get(clf) is not None:
            self.ds3_score_jarvis[clf] = -np.asarray(self.ds3_score_jarvis[clf], float)

    def _ds3_widened(self, t, half_ms=3.0, null_ms=40.0, pct=99.0):
        """The relative-sink score (Tarcsay et al. 2025) with the outer and
        middle contacts found where DS1's and DS2's mean sinks are deepest,
        looked for on the far side of each blade's source and past the
        analyzed band (5 contacts). The blade where the two types differ most
        is used (as backend/dsmix.relsink). Outer = the contact farther from
        the source. Score = (outer - middle) / (outer + middle) at +-3 ms;
        events whose two sinks together are under the 99th percentile of the
        same sum 40 ms away are unscored (nan)."""
        if not ((t == 1).any() and (t == 2).any()):
            return {"why": "one type only"}
        m1, m2 = self.csd_peak[t == 1].mean(axis=0), self.csd_peak[t == 2].mean(axis=0)
        best, same = None, None
        for blade in ("upper", "lower"):
            rows = self.far_rows(blade)
            if rows.size < 2:
                continue
            o, mm = int(rows[np.argmin(m1[rows])]), int(rows[np.argmin(m2[rows])])
            if not (m1[o] < 0 and m2[mm] < 0):
                continue
            if o == mm:
                same = o
                continue
            gain = (m2[o] - m1[o]) + (m1[mm] - m2[mm])
            if best is None or gain > best[0]:
                best = (gain, o, mm, blade)
        if best is None:
            if same is not None:
                return {"why": "DS1's and DS2's mean sinks are deepest at the same contact (%d) in both blades" % (self.contacts[same])}
            return {"why": "a type has no sink in either blade"}
        _, o, mm, blade = best
        src = self.landmarks["GU"] if blade == "upper" else self.landmarks["GL"]
        outer, middle = (o, mm) if abs(o - src) >= abs(mm - src) else (mm, o)
        so, sm = np.maximum(-self.csd_peak[:, outer], 0.0), np.maximum(-self.csd_peak[:, middle], 0.0)
        null = []
        for c0 in (-null_ms, null_ms):
            w = np.abs(self.t_ms - c0) <= half_ms
            null.append(np.maximum(-self.csd[:, outer][:, w].mean(axis=1), 0.0) + np.maximum(-self.csd[:, middle][:, w].mean(axis=1), 0.0))
        floor = float(np.percentile(np.concatenate(null), pct))
        tot = so + sm
        score = np.full(self.n, np.nan)
        ok = tot > floor
        score[ok] = (so[ok] - sm[ok]) / tot[ok]
        return {"score": score, "outer": outer, "middle": middle, "blade": blade, "floor": floor,
                "gap_um": abs(outer - middle) * SPACING_UM, "ds1_row": o, "ds2_row": mm,
                "outer_is_ds1": outer == o}

    # ------------------------------------------------------------ depth
    def _landmarks(self, m):
        """From the mean CSD at the DS peak over all events (bad rows filled):
        U, L   the main sink of the upper and of the lower blade (rows, sub-contact)
        GU, GL the source nearest each of them on the way to the other blade
               (the granule cell layer side of that blade); equal when there
               is one source between the blades
        """
        a, b = self.band
        cut = self.hump_cut_row
        if cut is None or cut <= a or cut > b:
            return None
        s1 = a + int(np.argmin(m[a:cut]))
        s2 = cut + int(np.argmin(m[cut:b + 1]))
        if s2 - s1 < 3 or m[s1] >= 0 or m[s2] >= 0:
            return None
        U, L = _centroid(-m, s1), _centroid(-m, s2)
        seg = m[s1:s2 + 1]
        top = float(seg.max())
        if top <= 0:
            return None
        pk = [i for i in range(1, seg.size - 1) if seg[i] >= seg[i - 1] and seg[i] >= seg[i + 1] and seg[i] >= 0.25 * top]
        if not pk:
            pk = [int(np.argmax(seg))]
        gu, gl = s1 + pk[0], s1 + pk[-1]
        GU, GL = _centroid(m, gu, 0.7), _centroid(m, gl, 0.7)
        # KCNT1 (2026-11-27): two source peaks inside ONE source lobe give the same centroid but for rounding (m306:
        # GU 48.9914, GL 48.9832), which read as "upper source below lower" and dropped the recording. Within a
        # hundredth of a contact they are the one source this function already allows ("equal when there is one").
        if GU > GL and GU - GL < 0.05:
            GU = GL = 0.5 * (GU + GL)
        if not (U < GU <= GL < L):
            return None
        # THE ROWS BETWEEN THE SINKS, WITHOUT THE SINKS (2026-11-18: "the rows in
        # between include the sinks ... that would confound the results"):
        # from where the upper sink's lobe ends (the mean CSD turns >= 0 below
        # its deepest row) to where the lower sink's lobe begins.
        zu = next((i for i in range(s1 + 1, s2) if m[i] >= 0), None)
        zl = next((i for i in range(s2 - 1, s1, -1) if m[i] >= 0), None)
        src_rows = list(range(zu, zl + 1)) if zu is not None and zl is not None and zl >= zu else []
        return {"src_rows": src_rows, "U": U, "L": L, "GU": GU, "GL": GL, "rowU": s1, "rowL": s2, "rowGU": gu, "rowGL": gl,
                "sinkU": float(-m[s1]), "sinkL": float(-m[s2]), "source": top,
                "blade_um": (L - U) * SPACING_UM, "gcl_to_sink_upper_um": (GU - U) * SPACING_UM, "gcl_to_sink_lower_um": (L - GL) * SPACING_UM,
                "source_gap_um": (GL - GU) * SPACING_UM}

    def depth_um(self, rows):
        """Microns below the middle of the analyzed band."""
        a, b = self.band
        return (np.asarray(rows, float) - (a + b) / 2.0) * SPACING_UM

    def u(self, rows):
        """Blade-to-blade position: 0 at the upper blade's main sink, 1 at the
        lower blade's. The same on every recording whatever the probe's track."""
        k = self.landmarks
        return (np.asarray(rows, float) - k["U"]) / (k["L"] - k["U"])

    def v(self, rows, blade):
        """Folded position within one blade ('upper' or 'lower'): 0 at the
        granule-layer source, 1 at the blade's main sink, above 1 farther out
        (distal, towards the outer molecular layer)."""
        k = self.landmarks
        r = np.asarray(rows, float)
        if blade == "upper":
            return (k["GU"] - r) / (k["GU"] - k["U"])
        return (r - k["GL"]) / (k["L"] - k["GL"])

    def on_u(self, profile, grid):
        """A 64-row depth profile resampled on a blade-to-blade grid (nan
        beyond the probe); bad rows are filled first."""
        p = fill_bad(profile, self.bad_rows)
        return np.interp(grid, self.u(np.arange(p.shape[-1])), p, left=np.nan, right=np.nan)

    def on_v(self, profile, blade, grid):
        """A 64-row depth profile resampled on one blade's folded grid."""
        p = fill_bad(profile, self.bad_rows)
        x = self.v(np.arange(p.shape[-1]), blade)
        o = np.argsort(x)
        return np.interp(grid, x[o], p[o], left=np.nan, right=np.nan)

    def blade_rows(self, blade, widen=5):
        """The rows of one blade's side of the analyzed band, widened past
        the band's end by `widen` contacts (the outer sinks often sit there)."""
        a, b = self.band
        cut = self.hump_cut_row
        if blade == "upper":
            return np.arange(max(0, a - widen), cut)
        return np.arange(cut, min(len(self.contacts) - 1, b + widen) + 1)

    def good(self, rows):
        """The rows that are not bad contacts."""
        return np.array([r for r in rows if r not in self.bad_rows], int)


def load(event_set="v6"):
    """event_set: 'v6' the Halo set (4,824 events; the main set) or 'v8' the
    No P-spikes set (4,177 events; stricter; used to see whether a result
    holds on a second cut of the same recordings)."""
    with open(os.path.join(DATA, "ds_%s.pkl" % event_set), "rb") as f:
        recs = [Rec(d) for d in pickle.load(f)]
    if event_set in ("v7", "v8"):
        # THE WINNER IS KEPT (2026-11-18): every event of the stricter sets
        # keeps the type and DS3 call it has under the Halo set's winner,
        # matched by time (5 ms). An event the Halo set does not hold gets
        # no type (0).
        base = by_lab(load("v6"))
        for r in recs:
            b = base.get(r.lab)
            if b is None or not b.winner or r.times_s is None or b.times_s is None:
                r.winner = r.winner_row = r.winner_si = None
                r.labels.pop("winner", None)
                continue
            o = np.argsort(b.times_s)
            bt = b.times_s[o]
            j = np.clip(np.searchsorted(bt, r.times_s), 1, bt.size - 1)
            j = np.where(np.abs(bt[j - 1] - r.times_s) <= np.abs(bt[j] - r.times_s), j - 1, j)
            hit = np.abs(bt[j] - r.times_s) <= 0.005
            idx = np.where(hit, o[j], -1)
            tb = b.types("winner")
            t = np.where(idx >= 0, tb[np.maximum(idx, 0)], 0)
            r.labels["winner"] = dict(b.labels["winner"], types=t, n1=int((t == 1).sum()), n2=int((t == 2).sum()), eligible=True)
            w = dict(b.ds3w["winner"])
            if "score" in w:
                w["score"] = np.where(idx >= 0, np.asarray(w["score"], float)[np.maximum(idx, 0)], np.nan)
            r.ds3w["winner"] = w
            r.naming["winner"] = b.naming.get("winner")
            r.winner, r.winner_row, r.winner_si = b.winner, b.winner_row, b.winner_si
            r.n_unmatched_v6 = int((idx < 0).sum())
    if event_set.startswith("b_"):
        # THE FILTER SETS (2026-11-18): the Halo events with their CSD and LFP
        # made again under another filter. The labels are held: every event
        # keeps the type, the name check and the DS3 call it has in the Halo
        # set (5-100 Hz). Only the measurements change.
        base = by_lab(load("v6"))
        for r in recs:
            b = base[r.lab]
            r.labels, r.naming, r.ds3w = b.labels, b.naming, b.ds3w
            r.ds3_gap_um, r.ds3_score, r.ds3_score_jarvis = b.ds3_gap_um, b.ds3_score, b.ds3_score_jarvis
            r.used, r.conv, r.opt = b.used, b.conv, b.opt
            r.winner, r.winner_row, r.winner_si = b.winner, b.winner_row, b.winner_si
    return recs


BANDS = {"b_ds": "5-100 Hz (the DS filter)", "b_none": "no filter (60 Hz notch only)", "b_1_100": "1-100 Hz",
         "b_1_300": "1-300 Hz", "b_5_300": "5-300 Hz", "b_5_50": "5-50 Hz", "b_10_40": "10-40 Hz"}


def by_lab(recs):
    return {r.lab: r for r in recs}


def meta(recs):
    """One dict per recording: the labels every test needs."""
    return [{"lab": r.lab, "group": r.group, "subgroup": r.subgroup, "ko": r.ko, "n": r.n, "dur_min": r.dur_min, "date": r.date,
             "year": r.year, "ok": r.ok, "n_bad": len(r.bad), "band_contacts": r.band[1] - r.band[0] + 1,
             "blade_um": None if r.landmarks is None else r.landmarks["blade_um"]} for r in recs]


if __name__ == "__main__":
    for r in load("v6"):
        k = r.landmarks
        print("%-4s %-4s %-4s n %4d %s" % (r.lab, r.group, r.subgroup, r.n, "no landmarks" if k is None else
              "U %.1f GU %.1f GL %.1f L %.1f | blade %4.0f um, GCL-sink upper %3.0f lower %3.0f, source gap %3.0f | used %s (%s)" % (
                  k["U"], k["GU"], k["GL"], k["L"], k["blade_um"], k["gcl_to_sink_upper_um"], k["gcl_to_sink_lower_um"], k["source_gap_um"],
                  r.used, "separable" if r.separable() else "not separable")))
