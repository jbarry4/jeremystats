"""Rename the in-between class: pathological dentate spikes (pDS) -> borderline transients (BTs), as decided 2026-11-23."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["pages_a.py", "pages_b.py", "pages_c.py", "figlib.py", "m6_package.py", "m1_stats.py"]
REPL = [
    ("Pathological dentate spikes (pDS): an in-between kind of event that appears only where IEDs do",
     "Borderline transients (BTs): an in-between kind of event, rare in every control and common in every IED+ mouse"),
    ("STORY 5 \\u00b7 FROM DS TOWARD IED \\u00b7 pDS", "STORY 5 \\u00b7 FROM DS TOWARD IED \\u00b7 BORDERLINE TRANSIENTS"),
    ("pDS (pathological DS)", "BT (borderline transient)"),
    ("pathological dentate spikes (pDS)", "borderline transients (BTs)"),
    ("pathological dentate spikes", "borderline transients (BTs)"),
    ("Pathological DS", "Borderline transients"),
    ("pathological DS (pDS, the in-between class)", "borderline transients (BT, the in-between class)"),
    ("pathological DS", "borderline transients"),
    ("What a pDS is", "What a BT is"),
    ("pDS per minute", "BTs per minute"),
    ("pDS and IEDs", "BTs and IEDs"),
    ("DS and pDS", "DS and BTs"),
    ("DS, pDS AND IEDs", "DS, BTs AND IEDs"),
    ("pDS have the footprint", "BTs have the footprint"),
    ("pDS put their current", "BTs put their current"),
    ("pDS look like", "BTs look like"),
    ("pDS fill the gap", "BTs fill the gap"),
    ("pDS share the DS's", "BTs share the DS's"),
    ("44 pDS", "44 BTs"),
    ("pDS counts", "BT counts"),
    ("pDS rate", "BT rate"),
    ("pDS class", "BT class"),
    ("removes pDS", "removes BTs"),
    ("%d pDS", "%d BT"),
    ("pDS: 0.56 to 1.89", "BTs: 0.56 to 1.89"),
    ("pDS (% of all)", "BTs (% of all)"),
    ("pDS vs DS", "BT vs DS"),
    ("IED vs pDS", "IED vs BT"),
    ("pDS %.0f", "BT %.0f"),
    ("pDS as brief", "BTs as brief"),
    ("07_story5_pathological_DS", "07_story5_borderline_transients"),
    ("08_story6_DS_pDS_IED_same_session", "08_story6_DS_BT_IED_same_session"),
    ("\"pDS\": C_PDS", "\"BT\": C_PDS"),
    ("\"TZ\": \"pDS\", \"pDS\": \"pDS\"", "\"TZ\": \"BT\", \"BT\": \"BT\""),
    ("[\"DS\", \"pDS\", \"IED\"]", "[\"DS\", \"BT\", \"IED\"]"),
    ("(\"5\", \"pDS\", \"Pathological DS\"", "(\"5\", \"BTs\", \"Borderline transients\""),
    ("(\"5\", \"pDS\",", "(\"5\", \"BTs\","),
    ("(\"pDS\", \"in-between events\"", "(\"BTs\", \"borderline transients\""),
    ("\"5  pDS\"", "\"5  BTs\""),
    ("pDS = the Root Canal classes", "BTs = the Root Canal classes"),
    ("\"pDS\": int(", "\"BT\": int("),
    ("\"pDS_per_min\"", "\"BT_per_min\""),
    ("pDS_IED_and_fast_power_per_mouse.csv", "BT_IED_and_fast_power_per_mouse.csv"),
    ("replace({\"TZ\": \"pDS\"})", "replace({\"TZ\": \"BT\"})"),
    ("DS_pDS_IED_events_five_IEDplus_sessions.csv", "DS_BT_IED_events_five_IEDplus_sessions.csv"),
    ("In-between events (pathological DS: inside both borders, or between the halos) per minute",
     "Borderline transients (BTs: inside both borders, or between the halos) per minute"),
    ("In-between events as a % of DS + in-between + IED events", "Borderline transients as a % of DS + BT + IED events"),
    ("Stories 5\\u20136", "Stories 5\\u20136"),
]
for f in FILES:
    p = os.path.join(HERE, f)
    s = open(p, encoding="utf-8").read()
    n0 = s.count("pDS")
    for a, b in REPL:
        s = s.replace(a, b)
    n1 = s.count("pDS")
    open(p, "w", encoding="utf-8").write(s)
    print(f, "pDS before", n0, "after", n1)
