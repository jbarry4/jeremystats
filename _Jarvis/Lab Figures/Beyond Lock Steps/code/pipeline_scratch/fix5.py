"""Standard terms only: no 'families', 'hybrids', 'splits', 'leads', 'shuffles'."""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def patch(name, pairs, extra=None):
    p = os.path.join(HERE, name)
    s = io.open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert s.count(a) >= 1, (name, a[:70])
        s = s.replace(a, b)
    if extra:
        s = extra(s)
    io.open(p, "w", encoding="utf-8").write(s)


# the measures' names, in one place
p = os.path.join(HERE, "deep_stats2.py")
s = io.open(p, encoding="utf-8").read()
if "RENAME" not in s:
    s = s.replace('BOTH = ("bite", "pca", "pca_gap", "delta", "delta_mid")', '''BOTH = ("bite", "pca", "pca_gap", "delta", "delta_mid")
RENAME = {"rate": "Event rate", "lfp_amp": "LFP amplitude", "lfp_ms": "LFP width (FWHM)", "sink_ms": "Sink duration (FWHM)",
          "sink_width": "Sink spatial width (FWHM)", "blade_um": "Distance between blade sinks", "amp_cv": "LFP amplitude CV",
          "iei_cv": "CV of inter-event intervals", "burst": "Inter-event intervals under 1 s", "si_best2": "DS1–DS2 separation index",
          "vote_agree": "Agreement between classifiers", "ds3_share_si": "DS3 share of events",
          "sink_asym": "Sink asymmetry, upper − lower blade", "src_net": "Source/sink ratio, granule layer",
          "lfp_at_src": "LFP ratio, granule layer / blades"}


def rename(rows):
    for r in rows:
        r["name"] = RENAME.get(r["key"], r["name"])
    return rows''')
    io.open(p, "w", encoding="utf-8").write(s)

patch("deep_figs.py", [
    ('    rows = FIN[6]["rows"]\n    n = len(rows)', '    rows = D2.rename(FIN[6]["rows"])\n    n = len(rows)'),
    ('"Two families: control m61"', '"DS1 and DS2 separable: control m61"'),
    ('"One family: control m60"', '"Not separable: control m60"'),
    ('ax.set_title("%s, separation %.2f" % (title, e["si"]), fontsize=FS, loc="left", pad=9)',
     'ax.set_title("%s (index %.2f)" % (title, e["si"]), fontsize=FS, loc="left", pad=9)'),
    ('(0, 0.2, "one family", "#F3F3F3"), (0.2, 0.5, "partly", "#E9E9E9"), (0.5, 1.0, "two families", "#DEDEDE")',
     '(0, 0.2, "not sep.", "#F3F3F3"), (0.2, 0.5, "partial", "#E9E9E9"), (0.5, 1.0, "separable", "#DEDEDE")'),
    ('ax.set_xlabel("Separation of the best split\\n(1 = no overlap between DS1 and DS2)", fontsize=FS)',
     'ax.set_xlabel("DS1–DS2 separation index\\n(1 = no overlap between DS1 and DS2)", fontsize=FS)'),
    ('ax.set_xlabel("Events, sorted by the split", fontsize=FS)', 'ax.set_xlabel("Events, sorted by classifier score", fontsize=FS)'),
    ('ax.set_ylabel("Events scored as hybrid, DS3 (%)", fontsize=FS)', 'ax.set_ylabel("Events classified as DS3 (%)", fontsize=FS)'),
    ('"dot: one recording, one split\\nline: median"', '"dot: one recording, one classifier\\nline: median"'),
    ('ax.set_xlabel("Distance between the contacts read as\\nouter and middle molecular layer (µm)", fontsize=FS)',
     'ax.set_xlabel("Distance between the outer and middle\\nmolecular layer contacts (µm)", fontsize=FS)'),
    ('"Where each family\'s sink sits, in the six recordings with two families"',
     '"Sink depth profiles of DS1 and DS2 in the six separable recordings"'),
    ('"sink only, each scaled to its own deepest;\\nline: the centre of each blade\'s sink"',
     '"sink only, each normalised to its maximum;\\nline: sink centroid in each blade"'),
    ('["Two\\nfamilies\\n(n = %d)" % len(grp[0]), "One or\\npartly\\n(n = %d)" % len(grp[1])]',
     '["Separable\\n(n = %d)" % len(grp[0]), "Not\\nseparable\\n(n = %d)" % len(grp[1])]'),
    ('ax.set_ylabel("DS1 sink beyond DS2 sink (µm)", fontsize=FS)', 'ax.set_ylabel("DS1 sink distal to DS2 sink (µm)", fontsize=FS)'),
    ('save(fig, "Fig2_families_and_hybrids")', 'save(fig, "Fig2_DS1_DS2_DS3_classification")'),
    ('ax.set_ylabel("Depth from the granule-layer\\nsource (µm)", fontsize=FS)', 'ax.set_ylabel("Depth from granule cell layer\\nsource (µm)", fontsize=FS)'),
    ('"Rank-biserial effect\\n(− lower in PTEN, + higher)"', '"Rank-biserial correlation\\n(− lower in PTEN, + higher)"'),
    ('"Dose: against % knockout, PTEN only"', '"Correlation with % knockout, PTEN only"'),
    ('"Spearman ρ\\n(− falls with knockout, + rises)"', '"Spearman ρ"'),
    ('After correction over these\\n%d tests the smallest q is %.2f:\\nno measure separates the groups."',
     'Benjamini–Hochberg correction\\nover these %d tests:\\nsmallest q = %.2f."'),
    ('ax.set_ylabel("CSD at the spike\\n(1 = mean depth of the two sinks)", fontsize=FS)',
     'ax.set_ylabel("CSD at the DS peak\\n(normalised to mean sink amplitude)", fontsize=FS)'),
    ('["upper\\nblade sink", "granule cells\\nand hilus", "lower\\nblade sink"]', '["upper\\nblade sink", "granule cell\\nlayers, hilus", "lower\\nblade sink"]'),
    ('ax.set_xlabel("Granule cells knocked out (%)", fontsize=FS)', 'ax.set_xlabel("PTEN knockout (% of granule cells)", fontsize=FS)'),
    ('ax.set_ylabel("Net current between the blades\\n(+ source; 1 = the sinks\' depth)", fontsize=FS)',
     'ax.set_ylabel("Mean CSD between blade sinks\\n(normalised to sink amplitude)", fontsize=FS)'),
    ('ax.set_xlabel("Smallest P among all %d tests tried,\\nmouse labels shuffled (1,000 times)" % fam["n_tests"], fontsize=FS)',
     'ax.set_xlabel("Minimum P across all %d tests,\\n1,000 permutations of group labels" % fam["n_tests"], fontsize=FS)'),
    ('"best in this data:\\nP = %.3f\\n\\n%.0f%% of shuffles\\ndo as well" % (fam["best"][1], 100 * fam["fw_p"])',
     '"observed minimum:\\nP = %.3f\\n\\nfamily-wise\\nP = %.2f" % (fam["best"][1], fam["fw_p"])'),
    ('"PTEN knockout, ordered by % of granule cells knocked out"', '"PTEN knockout, ordered by % of granule cells with knockout"'),
    ('"Depth from blade midpoint (µm)"', '"Depth from midpoint between blade sinks (µm)"'),
    ('"Source\\ngranule cells"', '"Source\\ngranule cell layer"'),
])

patch("deep_words.py", [
    ('rows = FIN[6]["rows"]', 'import deep_stats2 as D2\nrows = D2.rename(FIN[6]["rows"])'),
    ("Figure 2 | Two families of dentate spike are resolved in a third of recordings; elsewhere 'hybrid' events are a matter of spacing.",
     "Figure 2 | DS1 and DS2 are separable in six of 17 recordings; the DS3 share depends on contact spacing."),
    ("sorted by the recording's best split (DS1 blue bar, DS2 orange), and\neach family's mean (+- s.e.m.), in a recording that separates (a) and one that does not (b).",
     "sorted by classifier score (DS1 blue bar, DS2 orange), and\nthe mean of each type (+- s.e.m.), in a recording where DS1 and DS2 are separable (a) and one where they are not (b)."),
    ("c, Separation of the best of 15 splits per recording (1 - overlap between families / overlap within; chosen blind to group).",
     "c, DS1-DS2 separation index of the best of 15 classifiers per recording (1 - sink overlap between types / overlap within types;\nselected blind to genotype)."),
    ("d, Share of events scored as hybrid (DS3; relative sink within +-0.5, after Tarcsay et al. 2025) against the distance between\nthe two contacts read as outer and middle molecular layer, for every recording under every split.",
     "d, Share of events classified as DS3 (relative-sink score within +-0.5, after Tarcsay et al. 2025) against the distance between\nthe outer and middle molecular layer contacts, for every recording under every classifier."),
    ("e, The six recordings with two families. Sink only, each family scaled to its own deepest sink, DS1 to the left and DS2 to\nthe right of each axis; lines mark the centre of each blade's sink.",
     "e, The six separable recordings. Sink only, each type normalised to its maximum, DS1 to the left and DS2 to\nthe right of each axis; lines mark the sink centroid in each blade."),
    ("and its sink lies farther from the granule layer in both blades.", "and its sink lies distal to DS2's (farther from the granule cell layer) in both blades."),
    ("f, How far DS1's sink centre lies beyond DS2's (mean of the two blades): 163 µm in recordings with two families against\n59 µm in the rest",
     "f, Distance of the DS1 sink centroid distal to the DS2 sink centroid (mean of the two blades): 163 µm in separable recordings against\n59 µm in the rest"),
    ("Figure 3 | No measure separates PTEN from control; one lead for a planned test.",
     "Figure 3 | No measure differs between PTEN and control after correction; one exploratory association."),
    ("a, Fifteen measures chosen for what they mean.", "a, Fifteen pre-selected measures."),
    ("A classifier given all fifteen cannot tell a held-out\nmouse's group", "Leave-one-mouse-out logistic regression on all fifteen does not predict\ngenotype"),
    ("the same measures order held-out mice by knockout weakly\n(rho = %.2f, permutation P = %.3f).",
     "leave-one-mouse-out ridge regression predicts %% knockout weakly\n(rho = %.2f, permutation P = %.3f)."),
    ("b, Mean current at the spike between the two blade sinks (position scaled so the sinks sit at fixed points; current scaled to\nthe sinks' mean depth), by group (+- s.e.m.).",
     "b, Mean CSD at the DS peak between the two blade sinks (depth normalised to the inter-sink distance; CSD normalised to\nmean sink amplitude), by group (+- s.e.m.)."),
    ("c, The lead: the net current between the blades, a source in controls, falls towards zero as the knockout grows",
     "c, Exploratory: mean CSD between the blade sinks (a net source in controls) against % knockout".replace("%", "%%")),
    ("d, What the search gives by chance. Across everything tried (%d tests on %d measures) the smallest P in this data is %.3f;\nwith mouse labels shuffled, %.0f%% of 1,000 shuffles give one as small. The lead in c is therefore a hypothesis, not a result.",
     "d, Family-wise error. Across all %d tests on %d measures the minimum P is %.3f; in 1,000 permutations of the group labels\n%.0f%% give a minimum P at least as small. The association in c is therefore exploratory."),
    ("A planned test of control against", "A confirmatory test of control against"),
    ('["best split", "DS1 share under best split"]', '["best classifier", "DS1 share under best classifier"]'),
    ("b, The same for every recording", "b, The same for every recording"),
    ("Depth is measured from the midpoint between the two blade sinks.", "Depth is measured from the midpoint between the two blade sinks."),
    ("darker with the share of granule cells knocked out", "darker with the % of granule cells with knockout"),
])

patch("deep_unc.py", [
    ('rows = FIN[6]["rows"]', 'rows = D2.rename(FIN[6]["rows"])'),
])
print("ok")
