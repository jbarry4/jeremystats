import io
B = "C:\\Users\\Z390\\Desktop\\DS_PTEN_figures_2026-11-16\\battery\\"


def patch(fn, pairs):
    s = io.open(B + fn, encoding="utf-8").read()
    for a, b in pairs:
        assert s.count(a) == 1, (fn, a[:70], s.count(a))
        s = s.replace(a, b)
    io.open(B + fn, "w", encoding="utf-8", newline="\n").write(s)


EXC = '[m for m in json.load(open(os.path.join(HERE, "data", "meta.json"))) if m["lab"] not in ("m6",)]  # m6 excluded 2026-11-17 (dsdata.EXCLUDED)'
patch("harness.py", [
    ('META = json.load(open(os.path.join(HERE, "data", "meta.json")))', 'META = ' + EXC),
    ('("PTEN_vs_CTL", "PTEN (n 9) against control (n 8)", "two"),', '("PTEN_vs_CTL", "PTEN (n 9) against control (n 7)", "two"),'),
])
patch("analyze.py", [
    ('META = json.load(open(os.path.join(HERE, "data", "meta.json")))', 'META = ' + EXC),
])
patch("make_top10.py", [
    ('META = [m for m in json.load(open(os.path.join(HERE, "data", "meta.json"))) if m["n_v6"] >= 20]',
     'META = [m for m in json.load(open(os.path.join(HERE, "data", "meta.json"))) if m["n_v6"] >= 20 and m["lab"] not in ("m6",)]'),
])
patch("measures.py", [
    ('''        d = {"ds1": t == 1, "ds2": t == 2, "minor": t == minor, "major": t != minor}
        m3 = r.ds3(clf)
        if m3 is not None and m3.sum() >= MIN_TYPE:
            d["ds3"] = m3''', '''        d = {"ds1": t == 1, "ds2": t == 2, "minor": t == minor, "major": t != minor}
        m3 = r.ds3(clf)
        if m3 is not None and m3.sum() >= MIN_TYPE:
            d["ds3"] = m3
        if m3 is not None:
            # 2026-11-17: DS1 and DS2 with the DS3 events taken out
            d["ds1x"], d["ds2x"] = (t == 1) & ~m3, (t == 2) & ~m3
        else:
            d["ds1x"], d["ds2x"] = t == 1, t == 2''' ),
    ('''                if not (r.has(clf) and r.eligible(clf)) or r.ds3_score.get(clf) is None:
                    continue
                sc = np.asarray(r.ds3_score[clf], float)''', '''                sc = (r.ds3w.get(clf) or {}).get("score")
                if not (r.has(clf) and r.eligible(clf)) or sc is None:
                    continue
                sc = np.asarray(sc, float)'''),
    ('''    B.add("structure", "n_classifiers_separable", over(lambda v: float(sum(x >= dsdata.SEPARABLE for x in v))), "Number of eligible conventional classifiers with index 0.45 or more", "count", es, "", "over_classifiers")
''', ''),
    ('''        B.add("structure", "ds3_contact_gap_um", {r.lab: r.ds3_gap_um[clf] for r in recs if r.has(clf) and r.eligible(clf) and clf in r.ds3_gap_um},''',
     '''        B.add("structure", "ds3_contact_gap_um", {r.lab: r.ds3_gap_um[clf] for r in recs if r.has(clf) and r.eligible(clf) and r.ds3_gap_um.get(clf) is not None},'''),
])
print("ok")
