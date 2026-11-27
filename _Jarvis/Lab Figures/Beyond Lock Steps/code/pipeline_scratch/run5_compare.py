"""Battery run 5 (deduplicated, room v9) against run 4 (archived). Read only."""
import json
import os

import numpy as np
import pandas as pd

R = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16"
NEW = os.path.join(R, "battery")
OLD = os.path.join(R, "archive_run4_2026-11-19", "battery")
LEADS = os.path.join(R, "archive_run4_2026-11-19", "battery", "code")
out = {}


def summ(T):
    return {"tests": len(T), "p05": int((T.p < 0.05).sum()), "share": round(float((T.p < 0.05).mean()) * 100, 1),
            "p01": int((T.p < 0.01).sum()), "q_all": int((T.q_all < 0.10).sum()), "q_contrast": int((T.q_contrast < 0.10).sum()),
            "q_family": int((T.q_family < 0.10).sum()), "maxT10": int((T.p_maxT < 0.10).sum()), "maxT05": int((T.p_maxT < 0.05).sum())}


COLS = ["id", "contrast", "test", "p", "effect", "q_all", "q_contrast", "q_family", "p_maxT", "p_other_set", "rho_year", "rho_log_events"]
for m in ("merged", "merged_filters", "merged_around"):
    To = pd.read_pickle(os.path.join(OLD, m, "tests.pkl"))
    Tn = pd.read_pickle(os.path.join(NEW, m, "tests.pkl"))
    print("\n=====", m)
    print(" run 4:", summ(To))
    print(" run 5:", summ(Tn))
    for lab, T in (("run 4", To), ("run 5", Tn)):
        hit = T[(T.q_all < 0.10) | (T.q_contrast < 0.10) | (T.q_family < 0.10) | (T.p_maxT < 0.10)]
        for _, r in hit.iterrows():
            print("   %s survives: %s | %s | %s p %.2g q_c %.2f q_f %.2f maxT %.2f other set p %.2g rho_year %.2f" % (
                lab, r.id, r.contrast, r.test, r.p, r.q_contrast, r.q_family, r.p_maxT, r.p_other_set, r.rho_year))
    try:
        oo = json.load(open(os.path.join(OLD, m, "omnibus.json")))
        on = json.load(open(os.path.join(NEW, m, "omnibus.json")))
        print(" omnibus (shuffled labels) run 4:", json.dumps(oo)[:600])
        print(" omnibus (shuffled labels) run 5:", json.dumps(on)[:600])
    except Exception as exc:                             # noqa: BLE001
        print(" omnibus:", exc)
    # how much moved, test by test (same id, contrast, test)
    k = ["id", "contrast", "test"]
    J = To[k + ["p", "effect"]].merge(Tn[k + ["p", "effect"]], on=k, suffixes=("_4", "_5"))
    ok = np.isfinite(J.p_4) & np.isfinite(J.p_5)
    J = J[ok]
    print(" matched tests %d | P moved: median |log10 ratio| %.3f | 90th pct %.3f | effect sign flipped in %.1f%%" % (
        len(J), np.median(np.abs(np.log10(J.p_5.clip(1e-12) / J.p_4.clip(1e-12)))),
        np.percentile(np.abs(np.log10(J.p_5.clip(1e-12) / J.p_4.clip(1e-12))), 90),
        100 * float((np.sign(J.effect_4) != np.sign(J.effect_5)).mean())))
    print(" P<0.05 in run 4 only: %d | in run 5 only: %d | both: %d" % (((J.p_4 < .05) & (J.p_5 >= .05)).sum(),
          ((J.p_4 >= .05) & (J.p_5 < .05)).sum(), ((J.p_4 < .05) & (J.p_5 < .05)).sum()))
    out[m] = (To, Tn)


def row(T, lid, contrast):
    x = T[(T.id == lid) & (T.contrast == contrast)]
    return None if x.empty else x.iloc[0]


print("\n===== leads")
SRC = {"leads.json": "merged", "leads_ds3.json": "merged", "leads_general.json": "merged", "leads_band.json": "merged_filters",
       "leads_around.json": "merged_around"}
lead_rows = []
for js, m in SRC.items():
    To, Tn = out[m]
    for k, L in enumerate(json.load(open(os.path.join(NEW, js), encoding="utf-8")), 1):
        a, b = row(To, L["id"], L["contrast"]), row(Tn, L["id"], L["contrast"])
        if a is None or b is None:
            print(" %-18s %2d %-60s missing (old %s new %s)" % (js, k, L["id"], a is not None, b is not None))
            continue
        lead_rows.append({"set": js, "k": k, "id": L["id"], "contrast": L["contrast"], "title": L.get("title"), "test": b.test,
                          "p4": float(a.p), "p5": float(b.p), "e4": float(a.effect), "e5": float(b.effect),
                          "o4": float(a.p_other_set) if pd.notna(a.p_other_set) else None,
                          "o5": float(b.p_other_set) if pd.notna(b.p_other_set) else None})
        print(" %-18s %2d %-62s %-24s p %.3g -> %.3g | effect %+.2f -> %+.2f | other set p %s -> %s" % (
            js, k, L["id"][:62], L["contrast"], a.p, b.p, a.effect, b.effect,
            "%.2g" % a.p_other_set if pd.notna(a.p_other_set) else "-", "%.2g" % b.p_other_set if pd.notna(b.p_other_set) else "-"))
json.dump(lead_rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run5_leads.json"), "w"), indent=1)

# the lead rule of run 4: raw P < 0.05 on the Halo set, same sign and P < 0.10 on No P-spikes
print("\n===== the run 4 shortlist rule (P < 0.05 Halo, same sign + P < 0.10 No P-spikes), main battery")
for lab, T in (("run 4", out["merged"][0]), ("run 5", out["merged"][1])):
    s = T[(T.event_set == "v6") & (T.p < 0.05) & (T.p_other_set < 0.10) & (T.same_sign_other_set == 1)]
    print(" %s: %d tests, %d measures" % (lab, len(s), s.id.nunique()))
s4 = out["merged"][0]
s4 = set(map(tuple, s4[(s4.event_set == "v6") & (s4.p < 0.05) & (s4.p_other_set < 0.10) & (s4.same_sign_other_set == 1)][["id", "contrast"]].values))
s5 = out["merged"][1]
s5 = set(map(tuple, s5[(s5.event_set == "v6") & (s5.p < 0.05) & (s5.p_other_set < 0.10) & (s5.same_sign_other_set == 1)][["id", "contrast"]].values))
print(" pass in both: %d | run 4 only: %d | run 5 only: %d" % (len(s4 & s5), len(s4 - s5), len(s5 - s4)))
