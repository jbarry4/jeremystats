"""Lead words updated to battery run 5 (2026-11-19: room v9, duplicate stamps
removed, m1 on Lock's stamps). Only leads whose numbers moved are touched;
run 4's lists are in archive_run4_2026-11-19/battery/code/.
  python leads_run5_patch.py"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DROP = "No longer under 0.05 in run 5. "

P = {
    ("leads.json", 1): {
        "why": "All mice rho −0.49 (P = 0.052; No P-spikes set the same). Within PTEN rho −0.68 (P = 0.050). The lead the battery "
               "started from, still there once the sink rows are taken out, but now just over 0.05.",
        "against": "Run 4 had P = 0.042; with the sink rows in it was P = 0.016. m61 (control, 0.99) and m8 (IED−, 1.16) carry much of "
                   "the spread. Dividing by the sink means a change in sink size moves it too."},
    ("leads.json", 2): {
        "why": "Within PTEN rho −0.82 (P = 0.011; No P-spikes set P = 0.0045). Still the strongest dose relation among these leads, "
               "but weaker than in run 4 (rho −0.92, P = 0.0013). IED+ against IED− P = 0.063.",
        "against": "PTEN against control P = 0.53: controls span 0.19 to 0.45, most of the PTEN range. m5 (−0.01) is the lowest of "
                   "all. An LFP measure: the LFP mixes in activity from farther away than the CSD does."},
    ("leads.json", 3): {
        "why": "IED− 0.38 to 0.54, controls 0.05 to 0.33: still no overlap (P = 0.016; No P-spikes set the same; run 4 P = 0.006). "
               "Low knockout against control P = 0.036.",
        "against": "Five controls have a value now (m2 and m21 do not), which is most of why P rose. IED+ sits with the controls "
                   "(P = 0.69); so it is not knockout as such. Theta power is from one contact and bins are 4 s; behavior state "
                   "is not known."},
    ("leads.json", 5): {
        "why": "Within PTEN rho −0.89 (P = 0.012; No P-spikes set P = 0.034)."},
    ("leads.json", 6): {
        "why": "IED− against control P = 0.014 (No P-spikes set the same). Low knockout against control P = 0.028.",
        "against": "An LFP measure (it mixes in activity from farther away than the CSD). DS1 is a small group in most mice. m60 "
                   "(10 ms) is just under m1 (10.5 ms); m61 and m22 (9 ms) are just below the IED− range."},
    ("leads.json", 9): {
        "why": "Within PTEN rho −0.70 (P = 0.035; No P-spikes set the same; run 4 P = 0.027).",
        "against": "Whole-millisecond values, so many ties. Controls span 11 to 14 ms. Tracks the year of recording (rho +0.41)."},
    ("leads_ds3.json", 2): {
        "why": "Every PTEN value below every control (P = 0.016; No P-spikes set the same; run 4 P = 0.008).",
        "against": "Nine mice have 5 or more DS3 events (four controls; one IED−). Over all events the same lean is there in IED+ "
                   "mice (general lead 2), so this may not be special to DS3. Tracks the year of recording (rho +0.84)."},
    ("leads_ds3.json", 4): {
        "why": "All mice rho −0.57, P = 0.11 (No P-spikes set the same; run 4 P = 0.059). Shown because you asked about this one; "
               "it is not under 0.05.",
        "against": "Nine mice. When in the session depends on anesthesia and handling. Over all events there is no such drift."},
    ("leads_ds3.json", 5): {
        "why": "PTEN against control P = 0.95; IED+ against IED− P = 0.31. It looked as if controls had more because the IED− "
               "mice include three with almost none."},
    ("leads_general.json", 1): {
        "why": "Every IED+ value below every control (P = 0.0025; No P-spikes set P = 0.030). IED+ against IED− P = 0.016.",
        "against": "IED+ mice have more events, and more events can make a CV steadier (rho with event count −0.35)."},
    ("leads_general.json", 3): {
        "why": "All mice rho +0.68 (P = 0.004; No P-spikes set P = 0.012). PTEN against control P = 0.023.",
        "against": "Tracks the year of recording strongly (rho −0.67). Sampled at 1 kHz, so the times are whole milliseconds."},
    ("leads_general.json", 5): {
        "why": "All mice rho +0.64 (P = 0.008; No P-spikes set P = 0.002). PTEN against control P = 0.016."},
    ("leads_general.json", 6): {
        "title_prefix": DROP,
        "why": "Within PTEN rho +0.65 (P = 0.067; No P-spikes set P = 0.006). Run 4: rho +0.82, P = 0.011.",
        "against": "Under 0.05 only on the No P-spikes set now. Controls span 0.98 to 1.13; PTEN against control P = 0.92. m7 (1.26) "
                   "is the highest of all."},
    ("leads_general.json", 7): {
        "why": "Within PTEN rho −0.83 (P = 0.015; No P-spikes set P = 0.011). IED+ against IED− P = 0.036."},
    ("leads_general.json", 8): {
        "title_prefix": DROP,
        "why": "Low knockout against control P = 0.12 (No P-spikes set P = 0.38). Run 4: every low-knockout value above every "
               "control, P = 0.017.",
        "against": "Three low-knockout mice. High-knockout mice are like controls, so it was never a dose effect."},
    ("leads_general.json", 9): {
        "why": "P = 0.032 (No P-spikes set P = 0.016)."},
    ("leads_general.json", 10): {
        "why": "IED− against control P = 0.024 (No P-spikes set P = 0.16; run 4 P = 0.012). PTEN against control P = 0.055.",
        "against": "Not on the No P-spikes set. Tracks the year of recording (rho −0.47)."},
    ("leads_band.json", 1): {
        "why": "Every IED− value above every control (P = 0.012). Under the DS filter P = 0.32; with 1–100 Hz P = 0.042. So it lives "
               "below 5 Hz: a slow sink that starts before the DS.",
        "against": "Not on the 1–300 Hz copy (P = 0.16), which also keeps the slow part; m7 (0.96) and m1 (0.89) carry it. IED+ mice "
                   "look like controls. A slow drift unrelated to the DS would do the same; the before/after battery tests that "
                   "directly."},
    ("leads_band.json", 3): {
        "title_prefix": DROP,
        "why": "IED− against control P = 0.16 (run 4: no overlap, P = 0.006). 5–50 Hz P = 0.32; DS filter P = 0.79.",
        "against": "The difference was small to begin with (0.26 against 0.25 at the edges). A narrow filter rings, and ringing makes "
                   "widths depend on the filter as much as on the event."},
    ("leads_band.json", 4): {
        "why": "Within PTEN rho −0.85 (P = 0.006; run 4 P = 0.014). No filter P = 0.025, 1–300 Hz P = 0.011, 10–40 Hz P = 0.037, "
               "DS filter P = 0.059.",
        "against": "Gone at 5–50 Hz (P = 0.71). m8 (1.22) and m33 (0.96), the two lowest-knockout mice, carry the correlation."},
    ("leads_band.json", 5): {
        "title_prefix": DROP,
        "why": "IED+ against control P = 0.13 (run 4 P = 0.010). IED+ against IED− P = 0.016 still. 1–100 Hz P = 0.43; DS filter "
               "P = 0.43.",
        "against": "Not without any filter (P = 0.33). m59 (0.03) sits with IED+."},
    ("leads_around.json", 1): {
        "why": "All mice rho −0.72 (P = 0.0016; No P-spikes set P = 0.0046). PTEN against control P = 0.008; IED− and IED+ each "
               "below controls (P = 0.024, 0.048). The before/after version of filter lead 1: something slow is different just "
               "before the DS."},
    ("leads_around.json", 2): {
        "why": "All mice rho +0.67 (P = 0.009; No P-spikes set P = 0.036). IED+ against control P = 0.008.",
        "against": "Tracks the number of events (rho +0.36) and the year (rho −0.42). 100–250 Hz is near the top of what the 1 kHz "
                   "copy keeps (the decimation filter starts at 400 Hz). Whole shank: where it happens is not resolved here."},
    ("leads_around.json", 3): {
        "why": "Within PTEN rho +0.93 (P = 0.0008; No P-spikes set P = 0.017; run 4 P = 0.0002). IED+ 1.1 to 2.6, IED− 0.6 to 1.1.",
        "against": "Controls span 0.9 to 2.5 (m2), so PTEN against control P = 0.95. DS1 is a small group in most mice: lining up is "
                   "easier to see with few events, and the comparison with random moments of the same count only partly fixes that."},
    ("leads_around.json", 4): {
        "title_prefix": DROP,
        "why": "Within PTEN rho +0.64 (P = 0.096). Run 4: rho +1.00 over 8 mice, P = 0.00005. The change is m1 alone: its "
               "events moved with its Lock alignment, and its value went from −0.04 to +0.34, off the line.",
        "against": "The changes are small (log2 −0.21 to +0.44 over all mice). Controls span the whole range (m59 +0.44). Which "
                   "rows are 'toward CA1' depends on where the probe sat."},
}

for js in sorted({k[0] for k in P}):
    path = os.path.join(HERE, js)
    LL = json.load(open(path, encoding="utf-8"))
    for (f, k), ch in P.items():
        if f != js:
            continue
        L = LL[k - 1]
        if ch.get("title_prefix") and not L["title"].startswith(ch["title_prefix"]):
            L["title"] = ch["title_prefix"] + L["title"]
        for key in ("why", "against"):
            if key in ch:
                L[key] = ch[key]
    if js == "leads_ds3.json":
        # DS3 lead 3 (the paper's DS3 share, upper blade, IED- against control) cannot be had: m1 is no longer scorable there,
        # which leaves two IED- mice, too few for the test.
        LL = [L for L in LL if L["id"] != "structure|lit_ds3_share|v6|literature|upper"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(LL, fh, indent=1, ensure_ascii=False)
    print(js, len(LL))
