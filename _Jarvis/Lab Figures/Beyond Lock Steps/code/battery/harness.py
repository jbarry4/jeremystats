"""Every measure of the pilot battery goes through the same contrasts.

    from harness import Battery
    B = Battery("timing")                       # your agent name
    B.add(family="timing", name="rate_all", values={"m60": 14.1, ...},
          desc="Events per minute, all events", unit="1/min",
          event_set="v6", classifier="", variant="")
    B.save()                                    # also saved every 40 adds

`values`: one number per recording (mouse), keyed by lab name ("m60"). Leave
a recording out (or give nan) when the measure cannot be had there. m51 (5
events) is dropped by the harness whatever you pass.

Each measure gets every contrast below that its numbers allow. P values are
two-sided and RAW; corrections are made later, over everything, by the main
session. One row per (measure, contrast) lands in results/<agent>.pkl.
"""
import atexit
import itertools
import json
import math
import os
import pickle

import warnings

import numpy as np
from scipy import stats as st

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
META = [m for m in json.load(open(os.path.join(HERE, "data", "meta.json"))) if m["lab"] not in ("m6",)]  # m6 excluded 2026-11-17 (dsdata.EXCLUDED)
LABS = [m["lab"] for m in META]
M = {m["lab"]: m for m in META}
LOW_KO, HIGH_KO = 10.0, 15.0
_PERMS = {}

CONTRASTS = [
    # id, what, kind
    ("PTEN_vs_CTL", "PTEN (n 9) against control (n 7)", "two"),
    ("KO_dose_PTEN", "against % knockout, PTEN only (n 9)", "corr"),
    ("KO_dose_all", "against % knockout, all mice, controls at 0 (a mix of group and dose)", "corr"),
    ("highKO_vs_CTL", "PTEN with 15%+ knockout (n 6) against control", "two"),
    ("lowKO_vs_CTL", "PTEN under 10% knockout (n 3) against control", "two"),
    ("trend_CTL_lowKO_highKO", "ordered trend control < low < high knockout (Kendall tau-b = Jonckheere-Terpstra)", "trend"),
    ("IEDpos_vs_IEDneg", "PTEN IED+ (n 5) against PTEN IED- (n 4); IED+ mice also have the higher knockout", "two"),
    ("IEDpos_vs_CTL", "PTEN IED+ against control", "two"),
    ("IEDneg_vs_CTL", "PTEN IED- against control", "two"),
    ("trend_CTL_IEDneg_IEDpos", "ordered trend control < IED- < IED+ (Kendall tau-b)", "trend"),
    ("variance_PTEN_vs_CTL", "spread: Brown-Forsythe, PTEN against control", "var"),
]


def _perms(n):
    if n not in _PERMS:
        _PERMS[n] = np.array(list(itertools.permutations(range(n))), dtype=np.int8)
    return _PERMS[n]


def _two(a, b):
    """b against a: rank-biserial (+ when b is higher), Mann-Whitney p (exact
    when it can be), Welch p, Brunner-Munzel p."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    u = st.mannwhitneyu(b, a, alternative="two-sided")
    rb = 2.0 * u.statistic / (a.size * b.size) - 1.0
    try:
        pw = float(st.ttest_ind(b, a, equal_var=False).pvalue)
    except Exception:  # noqa: BLE001
        pw = float("nan")
    try:
        pb = float(st.brunnermunzel(b, a).pvalue)
    except Exception:  # noqa: BLE001
        pb = float("nan")
    return rb, float(u.pvalue), pw, pb


def _spearman(x, y):
    """rho and its p: exact (every permutation) for n <= 9 without ties,
    else the t approximation."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = x.size
    rx, ry = st.rankdata(x), st.rankdata(y)
    rho = float(np.corrcoef(rx, ry)[0, 1]) if np.ptp(rx) > 0 and np.ptp(ry) > 0 else float("nan")
    if not np.isfinite(rho):
        return rho, float("nan"), "none"
    if n <= 9 and np.unique(x).size == n and np.unique(y).size == n:
        cx, cy = rx - rx.mean(), ry - ry.mean()
        den = math.sqrt(float((cx ** 2).sum() * (cy ** 2).sum()))
        null = (cx[_perms(n)] @ cy) / den
        return rho, float((np.abs(null) >= abs(rho) - 1e-12).mean()), "exact"
    return rho, float(st.spearmanr(x, y).pvalue), "t"


class Battery(object):
    def __init__(self, agent, outdir=None):
        self.agent = str(agent)
        self.outdir = outdir or os.path.join(HERE, "results")
        os.makedirs(self.outdir, exist_ok=True)
        self.measures, self.rows, self._dirty = {}, {}, 0
        atexit.register(self.save)

    # ------------------------------------------------------------------
    def add(self, family, name, values, desc, unit="", event_set="v6", classifier="", variant=""):
        mid = "|".join([str(family), str(name), str(event_set), str(classifier), str(variant)])
        nkey = "n_%s" % event_set if ("n_%s" % event_set) in META[0] else "n_v6"
        v = {}
        for lab in LABS:
            x = values.get(lab) if hasattr(values, "get") else None
            try:
                x = float(x)
            except (TypeError, ValueError):
                x = float("nan")
            v[lab] = x if (np.isfinite(x) and M[lab][nkey] >= 20) else float("nan")
        arr = np.array([v[lab] for lab in LABS])
        fin = np.isfinite(arr)
        rec = {"id": mid, "agent": self.agent, "family": family, "name": name, "desc": desc, "unit": unit, "event_set": event_set,
               "classifier": classifier, "variant": variant, "values": v, "n_finite": int(fin.sum())}
        if fin.sum() >= 6 and np.ptp(arr[fin]) > 0:
            for key, conf in (("rho_log_events", [math.log(max(M[lab][nkey], 1)) for lab in LABS]), ("rho_minutes", [M[lab]["dur_min"] for lab in LABS]),
                              ("rho_year", [M[lab]["year"] for lab in LABS]), ("rho_bad_contacts", [M[lab]["n_bad"] for lab in LABS]),
                              ("rho_band_contacts", [M[lab]["band_contacts"] for lab in LABS]),
                              ("rho_blade_um", [M[lab]["blade_um"] if M[lab]["blade_um"] is not None else float("nan") for lab in LABS])):
                c = np.array(conf, float)
                ok = fin & np.isfinite(c)
                rec[key] = float(st.spearmanr(arr[ok], c[ok]).correlation) if ok.sum() >= 6 and np.ptp(c[ok]) > 0 else float("nan")
        self.measures[mid] = rec
        self.rows[mid] = self._contrasts(mid, rec, arr, fin) if (fin.sum() >= 6 and np.ptp(arr[fin]) > 0) else []
        self._dirty += 1
        if self._dirty >= 40:
            self.save()
        return mid

    def _contrasts(self, mid, rec, arr, fin):
        g = np.array([M[lab]["group"] for lab in LABS])
        sg = np.array([M[lab]["subgroup"] for lab in LABS])
        ko = np.array([M[lab]["ko"] for lab in LABS], float)
        lvl = np.where(g == "CTL", 0, np.where(ko < LOW_KO, 1, np.where(ko >= HIGH_KO, 2, -1)))
        iedl = np.where(sg == "CTL", 0, np.where(sg == "IED-", 1, 2))
        base = {k: rec[k] for k in ("id", "agent", "family", "name", "event_set", "classifier", "variant")}
        out = []

        def two(cid, mask_a, mask_b, min_a=4, min_b=3):
            a, b = arr[fin & mask_a], arr[fin & mask_b]
            if a.size < min_a or b.size < min_b or (np.ptp(np.concatenate([a, b])) == 0):
                return
            rb, p, pw, pb = _two(a, b)
            out.append(dict(base, contrast=cid, test="Mann-Whitney", n_a=int(a.size), n_b=int(b.size), est_a=float(np.median(a)),
                            est_b=float(np.median(b)), effect=rb, effect_kind="rank-biserial (+ = second group higher)", p=p,
                            p_alt=pw, alt_kind="Welch t", p_alt2=pb, alt2_kind="Brunner-Munzel"))

        def corr(cid, mask, x, min_n=6):
            ok = fin & mask
            if ok.sum() < min_n or np.ptp(arr[ok]) == 0 or np.ptp(x[ok]) == 0:
                return
            rho, p, how = _spearman(x[ok], arr[ok])
            kt = st.kendalltau(x[ok], arr[ok])
            try:
                pp = float(st.pearsonr(x[ok], arr[ok])[1])
            except Exception:  # noqa: BLE001
                pp = float("nan")
            out.append(dict(base, contrast=cid, test="Spearman (%s)" % how, n_a=int(ok.sum()), n_b=0, est_a=float("nan"), est_b=float("nan"),
                            effect=rho, effect_kind="Spearman rho", p=p, p_alt=float(kt.pvalue), alt_kind="Kendall tau",
                            p_alt2=pp, alt2_kind="Pearson"))

        def trend(cid, level):
            ok = fin & (level >= 0)
            if ok.sum() < 9 or np.unique(level[ok]).size < 3 or np.ptp(arr[ok]) == 0:
                return
            kt = st.kendalltau(level[ok], arr[ok])
            kw = st.kruskal(*[arr[ok & (level == k)] for k in (0, 1, 2)])
            out.append(dict(base, contrast=cid, test="Kendall tau-b trend", n_a=int(ok.sum()), n_b=0, est_a=float(np.median(arr[ok & (level == 0)])),
                            est_b=float(np.median(arr[ok & (level == 2)])), effect=float(kt.correlation), effect_kind="Kendall tau-b",
                            p=float(kt.pvalue), p_alt=float(kw.pvalue), alt_kind="Kruskal-Wallis (unordered)", p_alt2=float("nan"), alt2_kind=""))

        two("PTEN_vs_CTL", g == "CTL", g == "PTEN")
        corr("KO_dose_PTEN", g == "PTEN", ko)
        corr("KO_dose_all", np.ones(arr.size, bool), ko, 9)
        two("highKO_vs_CTL", g == "CTL", (g == "PTEN") & (ko >= HIGH_KO))
        two("lowKO_vs_CTL", g == "CTL", (g == "PTEN") & (ko < LOW_KO))
        trend("trend_CTL_lowKO_highKO", lvl)
        two("IEDpos_vs_IEDneg", sg == "IED-", sg == "IED+", 3, 3)
        two("IEDpos_vs_CTL", g == "CTL", sg == "IED+")
        two("IEDneg_vs_CTL", g == "CTL", sg == "IED-")
        trend("trend_CTL_IEDneg_IEDpos", iedl)
        a, b = arr[fin & (g == "CTL")], arr[fin & (g == "PTEN")]
        if a.size >= 5 and b.size >= 5:
            try:
                lv = st.levene(a, b, center="median")
                ma, mb = st.median_abs_deviation(a), st.median_abs_deviation(b)
                out.append(dict(base, contrast="variance_PTEN_vs_CTL", test="Brown-Forsythe", n_a=int(a.size), n_b=int(b.size), est_a=float(ma),
                                est_b=float(mb), effect=float(math.log((mb + 1e-12) / (ma + 1e-12))), effect_kind="log ratio of MADs (+ = PTEN more spread)",
                                p=float(lv.pvalue), p_alt=float("nan"), alt_kind="", p_alt2=float("nan"), alt2_kind=""))
            except Exception:  # noqa: BLE001
                pass
        return out

    # ------------------------------------------------------------------
    def save(self):
        path = os.path.join(self.outdir, "%s.pkl" % self.agent)
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            pickle.dump({"agent": self.agent, "measures": self.measures, "rows": [r for rr in self.rows.values() for r in rr]}, f, protocol=4)
        os.replace(tmp, path)
        self._dirty = 0
        return path

    def count(self):
        return len(self.measures), sum(len(r) for r in self.rows.values())

    def top(self, k=25, contrast=None):
        """The k smallest raw p (a quick look; not a result)."""
        rows = [r for rr in self.rows.values() for r in rr if np.isfinite(r["p"]) and (contrast is None or r["contrast"] == contrast)]
        rows.sort(key=lambda r: r["p"])
        return "\n".join("p %.4f  %-24s eff %+.2f  %s" % (r["p"], r["contrast"], r["effect"], r["id"]) for r in rows[:k])

    def describe(self, mid):
        """One measure's numbers, by group (to check them by eye)."""
        v = self.measures[mid]["values"]
        bits = []
        for name, labs in (("CTL", [m["lab"] for m in META if m["group"] == "CTL"]), ("IED-", [m["lab"] for m in META if m["subgroup"] == "IED-"]),
                           ("IED+", [m["lab"] for m in META if m["subgroup"] == "IED+"])):
            bits.append("%s: %s" % (name, " ".join("%s=%.3g" % (lab, v[lab]) for lab in labs if np.isfinite(v[lab]))))
        return mid + "\n   " + "\n   ".join(bits)
