import io
P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\dsdata.py"
s = io.open(P, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, a[:60]
    s = s.replace(a, b)


rep('''MIN_EVENTS = 20                 # a recording under this is left out of every test (m51)
''', '''MIN_EVENTS = 20                 # a recording under this is left out of every test (m51)
EXCLUDED = {"m6": "confounding factors during the experiment (the lab, 2026-11-17)"}
NAME_MIN_UM = 25.0              # half a contact: closer than this, the two types' sinks are "at the same place"
''')
rep('''        self.ok = self.n >= MIN_EVENTS
''', '''        self.excluded = EXCLUDED.get(self.lab)
        self.ok = self.n >= MIN_EVENTS and not self.excluded
''')
rep('''        self.landmarks = self._landmarks(self.mean_csd_peak)
''', '''        self.landmarks = self._landmarks(self.mean_csd_peak)
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
''')
rep('''    def ds3(self, clf, cut=0.5):
        """True where the event is DS3 under this classifier (relative sink
        within +-cut), or None when DS3 cannot be scored (DS1's and DS2's
        mean sinks peak at the same contact)."""
        s = self.ds3_score.get(clf)
        if s is None:
            return None
        s = np.asarray(s, float)
        return np.isfinite(s) & (np.abs(s) <= cut)
''', '''    def ds3(self, clf, cut=0.5, which="widened"):
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
''')
rep('''    # ------------------------------------------------------------ depth
''', '''    # ------------------------------------------------------------ names, DS3
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
''')
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
