"""Volume conduction: how tabs 11 and 12 dealt with it, in words, for the
Monolith (tab 11's card) and Joe's site (its own section) alike
(Shahriar, 2026-11-05).

Coherence counts any steady phase relation, including the zero-lag one a
single signal makes when it reaches two electrodes at once, through the
tissue or through a shared reference. Nothing new is tested here: this
reads what was already measured (tab 11's pooled spectra and reference
check, the bipolar check behind the methods, every set of rats' Late vs
Early) and says what each guard found, and what is still open.

    build(progress)  measure, word it, write joepub/conduction.json
    result()         the last build, or None

build() runs with joepub's (both the drawing and `joepub words`); it reads
the cached day spectra, so it needs no recordings.
"""
import json
import os
import time

import numpy as np

from . import evenmore as E
from . import joe

SCHEMA = 1


def _root(*parts):
    from . import monolith as MO
    return MO._path("joepub", *parts)


def _read(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _f2(v):
    return ("%.2f" % v).replace("-", "−")


def _rng(xs, fmt=_f2):
    lo, hi = fmt(min(xs)), fmt(max(xs))
    return ("%s to %s" if lo[:1] in "+−" or hi[:1] in "+−" else "%s–%s") % (lo, hi)


def lag_table(days):
    """Each rat-day's gamma on the 10 s baseline, over every valid wire
    pair: coherence, imaginary coherence (the part with a lag), and
    coherence within one side against across the two."""
    wi = E.WINS.index("base10")
    gm = joe.band_mask(E.FREQS, 30, 90)
    ipsi = np.array([c[2] == "ipsi" for c in E.COMBOS])
    out = []
    for (r, d), (a, _m) in sorted(days.items()):
        ok = a["nseg"][wi] > 0
        if not ok.any():
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            cohy = (a["sab"][wi] / np.sqrt(a["saa"][wi] * a["sbb"][wi]))[..., gm]        # (P, C, F)
        c2 = np.abs(cohy) ** 2
        im = np.abs(np.imag(cohy))
        side = lambda m: float(np.nanmean(c2[:, m][ok[:, m]])) if ok[:, m].any() else None   # noqa: E731
        out.append({"rat": int(r), "day": d, "coh": float(np.nanmean(c2[ok])), "icoh": float(np.nanmean(im[ok])),
                    "ipsi": side(ipsi), "contra": side(~ipsi)})
    return out


def by_set():
    """Each pair and band that passes Late vs Early (FDR) in any set of
    rats, with its ratio, p and q in every set."""
    R = {k: E.result(k) for k, _s, _d in E.RATSETS}
    R = {k: v for k, v in R.items() if v}
    keys = []
    for v in R.values():
        for B in v["bands"]:
            for x in B["phase1"]["pairs"]:
                if x and E.sig(x.get("a2"), "fdr") and (x["pair"], B["band"]) not in keys:
                    keys.append((x["pair"], B["band"]))
    keys.sort(key=lambda k: (k[1] != "theta", k[0]))
    rows = []
    for p, b in keys:
        cells = {}
        for k, v in R.items():
            B = next(z for z in v["bands"] if z["band"] == b)
            x = next((z for z in B["phase1"]["pairs"] if z and z["pair"] == p), None)
            a2 = (x or {}).get("a2") or {}
            cells[k] = {"ratio": a2.get("ratio"), "p": a2.get("p"), "q": a2.get("q"), "fdr": E.sig(a2, "fdr"), "raw": E.sig(a2, "raw")}
        rows.append({"pair": E.PAIR_SAY[p], "band": b, "sets": cells})
    return [{"key": k, "say": s} for k, s, _d in E.RATSETS if k in R], rows


def _cell(c):
    if not c or c.get("ratio") is None:
        return "not tested"
    q = c.get("q")
    return "×%.2f, q %s%s" % (c["ratio"], ("< .001" if q < 0.001 else ("%.3f" % q).lstrip("0")) if q is not None else "n/a",
                              " *" if c.get("fdr") else "")


def build(progress=None):
    say = progress or (lambda s: None)
    say("volume conduction: reading the day spectra")
    EM = E.result("all") or {}
    rc = sorted(EM.get("reference_check") or [], key=lambda x: -x["hg"])
    flagged = [x for x in rc if x["rat"] in (3, 4) and (x["rat"] == 3 or x["day"] == "Precon1")]
    rest = [x for x in rc if x not in flagged]
    lag = lag_table(E.load_days())
    lagf = [x for x in lag if any(x["rat"] == f["rat"] and x["day"] == f["day"] for f in flagged)]
    lagr = [x for x in lag if x not in lagf]
    j3 = next((x for x in lag if x["rat"] == 3 and x["day"] == "Precon4"), None)
    bip = _read(_root("bipolar.json")) or {}
    # the bipolar check's gamma per wire pair: one rat's, or (None) every rat's but J3's and J4's
    gam = lambda rat, kind: [v for e in bip.values() if (e.get("rat") == rat if rat else e.get("rat") not in (3, 4))   # noqa: E731
                             for v in e[kind]["gamma"] if v is not None]
    sets, held = by_set()
    steps = []

    steps.append({"key": "self", "title": "Each rat is compared with itself",
                  "line": "A steady share of conducted signal sits on both sides of every comparison, so it cannot make a change by itself.",
                  "more": [
                      "Every test compares a rat’s Late session (Precon4) with its own Early session (Precon1), or a cue with the baseline "
                      "just before it in the same trial. Between those, the electrodes, the reference and the tissue between them stay where "
                      "they are, and so does how much of one region’s signal the other electrode picks up.",
                      "It does not remove everything. Conducted coherence grows with the power of its source, so a region whose power "
                      "changed could change the coherence its neighbours record. That is why power in each region is analysed beside "
                      "coherence (the power figures): a coherence change with no power change in the same band is the safer reading."]})

    if rc:
        steps.append({"key": "screen", "title": "Every recording was screened for one signal on every wire",
                      "line": "%s of %d recordings carried it (%s); the rest were nowhere near." % (
                          len(flagged), len(rc), ", ".join("J%d %s" % (x["rat"], x["day"]) for x in flagged)),
                      "more": [
                          "A contaminated reference is volume conduction at its worst: whatever the reference picks up is in every wire at "
                          "once. Three marks were measured on each recording’s 10 s baselines, none of them used by any test: coherence "
                          "between regions at 75–90 Hz (between distant regions it should be small), how much higher that is than at "
                          "4–8 Hz (coherence from the brain usually falls with frequency), and the typical phase of the 30–90 Hz "
                          "cross-spectrum (a shared signal arrives everywhere at 0°).",
                          "The %s marked recordings stood apart on all three at once: coherence %s, a rise of %s and a phase of %s. The "
                          "other %d had coherence %s, a rise of %s and a phase of %s, so the cut needs no fine judgement." % (
                              len(flagged), _rng([x["hg"] for x in flagged]), _rng([x["rise"] for x in flagged], lambda v: ("%+.2f" % v).replace("-", "−")),
                              _rng([x["phase"] for x in flagged], lambda v: "%.0f°" % v),
                              len(rest), _rng([x["hg"] for x in rest]), _rng([x["rise"] for x in rest], lambda v: ("%+.2f" % v).replace("-", "−")),
                              _rng([x["phase"] for x in rest], lambda v: "%.0f°" % v))],
                      "table": {"head": ["Recording", "Coherence at 75–90 Hz", "Rise from 4–8 Hz", "Phase at 30–90 Hz", ""],
                                "rows": [["J%d %s" % (x["rat"], x["day"]), _f2(x["hg"]), ("%+.2f" % x["rise"]).replace("-", "−"),
                                          "%.0f°" % x["phase"], "marked" if x in flagged else ""] for x in rc]}})

    if j3 and lagr:
        more = [
            "Imaginary coherence keeps only the part of coherence that has a time lag, which a shared signal cannot make. In J3’s "
            "Precon4 baseline, gamma coherence was %s but its imaginary coherence %s, inside the other recordings’ %s. So nearly all of "
            "J3’s excess was at zero lag: a shared signal, not two regions in step." % (_f2(j3["coh"]), _f2(j3["icoh"]),
                                                                                      _rng([x["icoh"] for x in lagr]))]
        if j3.get("contra") is not None and j3.get("ipsi") is not None:
            more.append("A source inside the brain fades with distance; a reference does not. J3’s coherence was as high between the two "
                        "sides of the brain (%s) as within one side (%s)." % (_f2(j3["contra"]), _f2(j3["ipsi"])))
        if gam(3, "ref") and gam(None, "bip"):
            more.append("Subtracting a region’s two wires from each other (a local bipolar signal) cancels anything both wires share, "
                        "the reference included. It took J3’s gamma coherence from a median of %s to %s. It lowers every rat, though (the "
                        "others to a median of %s), because neighbouring wires also share real signal, so it was used only as a check, "
                        "never for the tests." % (_f2(float(np.median(gam(3, "ref")))), _f2(float(np.median(gam(3, "bip")))),
                                                  _f2(float(np.median(gam(None, "bip"))))))
        steps.append({"key": "lag", "title": "What the screen found is at zero lag",
                      "line": "J3’s high gamma coherence (%s) had an ordinary lagged part (%s); nearly all of the excess was at 0°." % (
                          _f2(j3["coh"]), _f2(j3["icoh"])),
                      "more": more,
                      "table": {"head": ["Recording", "Gamma coherence", "Imaginary coherence", "Within a side", "Across sides"],
                                "rows": [["J%d %s%s" % (x["rat"], x["day"], " (marked)" if x in lagf else ""), _f2(x["coh"]), _f2(x["icoh"]),
                                          _f2(x["ipsi"]) if x["ipsi"] is not None else "n/a", _f2(x["contra"]) if x["contra"] is not None else "n/a"]
                                         for x in lag]}})

    if held:
        both = [r for r in held if r["sets"].get("all", {}).get("fdr") and r["sets"].get("no34", {}).get("fdr")]
        steps.append({"key": "sets", "title": "Every analysis was run again without J3, without J4 and without both",
                      "line": "%s of the %d coherence changes found with every rat also pass without J3 and J4." % (
                          len(both), sum(1 for r in held if r["sets"].get("all", {}).get("fdr"))),
                      "more": [
                          "Each run without them fits every model again, with its own correction for many tests, its own follow-ups and "
                          "its own checks; the Rats switch shows any figure either way. A rat is left out whole, not one of its sessions, "
                          "because every test compares a rat’s two sessions.",
                          "The table is every pair whose Late against Early passes (q < .05, corrected across the ten pairs) in any set: "
                          "the ratio is Late ÷ Early, and * marks a pass. Changes that pass only without J3 and J4 may have been masked "
                          "by their shared signal, which adds the same coherence to every pair; read them with the reference switch "
                          "below in mind."],
                      "table": {"head": ["Pair", "Band"] + [s["say"] for s in sets],
                                "rows": [[r["pair"], r["band"].capitalize()] + [_cell(r["sets"].get(s["key"])) for s in sets] for r in held]}})

    steps.append({"key": "measures", "title": "Measures that ignore zero lag were computed too",
                  "line": "Imaginary coherence and the phase-lag index followed up the proposal’s comparisons and ran through the whole survey.",
                  "more": [
                      "The phase-lag index asks only whether one region is ahead of the other more often than behind; a phase difference "
                      "of exactly 0° (or 180°), which a shared signal makes, counts for nothing. Imaginary coherence does the same for "
                      "coherence (Nolte et al., 2004; Stam et al., 2007).",
                      "In the planned comparisons of the proposal, both were computed for every pair whose coherence changed. The "
                      "exploratory survey across 1–55 Hz carried imaginary coherence, the phase-lag index, its weighted and debiased "
                      "forms (Vinck et al., 2011) and the orthogonalised amplitude correlation for every pair, beside coherence."]})

    steps.append({"key": "granger", "title": "Direction is read with the same caution",
                  "line": "A shared signal can raise Granger causality both ways at once; each Granger figure says whether its pattern holds without J3 and J4.",
                  "more": [
                      "Granger causality was computed only for the pairs whose coherence changed, so it inherits whatever coherence "
                      "carries. A rise in both directions together is what a shared signal would make, which is why every Granger figure "
                      "has a note comparing it with the same pair without J3 and J4."]})

    steps.append({"key": "switch", "title": "J8, J9 and J10 changed reference between sessions",
                  "line": "Not a shared signal (they passed the screen), but a change between Early and Late that is not the brain’s.",
                  "more": [
                      "The recording headers say these three were referenced to Reference 1 on Precon1 and to Subject Ground on "
                      "Precon4. None of them shows the signature, but how much of a common signal reaches every wire depends on the "
                      "reference, so a Late against Early change in them could partly be the switch. The methods name it as a "
                      "confound."]})

    opens = [
        "The coherence tests use magnitude-squared coherence, which includes any zero-lag part. They have not been repeated on "
        "imaginary coherence, which would say whether each change is in the lagged part. The spectra to do it are already measured.",
        "No analysis leaves out J8, J9 and J10 together, so the reference switch is named but not tested.",
        "The recordings were analysed against their reference, not re-referenced (bipolar or current source density): with two "
        "wires a region, a local bipolar signal removes much of what is being measured, so it served only as a check."]
    out = {"ok": True, "schema": SCHEMA, "made": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "title": "Volume conduction: how it was handled",
           "say": "One signal reaching two electrodes at once, through the tissue or through a shared reference, makes coherence "
                  "between regions that are not communicating. What was done about it, what each step found, and what is still open.",
           "what": [
               "Electrical activity spreads through the brain and is picked up, weaker, by electrodes some distance from where it "
               "starts. When one source reaches two electrodes, both record it at the same instant, and their coherence rises "
               "although the two regions are not working together. The reference does the same thing more strongly: whatever it "
               "picks up appears on every wire at once.",
               "Both leave the same mark: the shared part arrives with no time lag (a phase of 0°). Two regions that really are "
               "coupled usually show some lag, because signals take time to travel between them. Every step below uses that."],
           "steps": steps, "open": opens,
           "numbers": {"reference_check": rc, "lag": lag, "held": held, "sets": sets}}
    joe._write(_root("conduction.json"), out)
    say("volume conduction: worded")
    return out


def result():
    return _read(_root("conduction.json"))


if __name__ == "__main__":
    from . import monolith as MO
    MO.configure(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "GUI_logs"))
    o = build(progress=print)
    for s in o["steps"]:
        print("-", s["title"], ":", s["line"])
