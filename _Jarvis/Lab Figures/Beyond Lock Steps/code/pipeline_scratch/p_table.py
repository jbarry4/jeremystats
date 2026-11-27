import io
P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_table.py"
s = io.open(P, encoding="utf-8").read()


def rep(a, b, cnt=1):
    global s
    assert s.count(a) == cnt, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('round10/Summary_table', 'round11/Summary_table')
rep('OUT = os.path.join(os.path.dirname(dsdata.HERE), "round10")', 'OUT = os.path.join(os.path.dirname(dsdata.HERE), "round11")')
rep('recs = dsdata.load("v6")', 'recs = [r for r in dsdata.load("v6") if not r.excluded]')
rep('''    d["sep"] = bool(r.used and r.separable())
''', '''    d["renamed"] = bool(r.used and "types_jarvis" in r.labels[r.used])
    d["names"] = r.naming.get(r.used, {}).get("verdict") if r.used else None
''')
rep('''"Halo set (4,824 events). Cell: separation index (1 = no overlap between DS1 and DS2; 0.45 or more = separable). Gray italic: the classifier is not eligible there "
        "(one type under 5% of events). Red box: the best eligible classifier."''',
    '''"Halo set; m6 left out (confounding factors during the experiment). Cell: separation index (1 = no overlap between DS1 and DS2, 0 = as much overlap as within a type). "
        "Gray italic: the classifier is not eligible there (one type under 5% of events). Red box: the best eligible classifier."''')
rep('''            fontweight="bold" if (eligible and not pct and v >= dsdata.SEPARABLE) else "normal")''', '''            fontweight="normal")''')
rep('''        if d["sep"]:
            ax.text(xe + 1, y + RH / 2, "separable", fontsize=FS_S - 0.5, va="center", color=Hs.GREEN, fontweight="bold")''',
    '''        if d["names"] in ("swapped", "same place", "blades disagree"):
            ax.text(xe + 1, y + RH / 2, {"swapped": "names swapped from Jarvis's", "same place": "DS1, DS2 names arbitrary", "blades disagree": "names uncertain"}[d["names"]],
                    fontsize=FS_S - 0.5, va="center", color=RED)''')
rep('''"DS1 % and DS3 %: under the best eligible classifier.''', '''"DS1 % and DS3 %: under the best eligible classifier; names checked against the anatomy (DS1 = sink farther from the cell layer; see the sanity check); DS3 layers looked for past the band.''')
rep('''"DS3 share paper upper", "DS3 share paper lower", "separable"])''', '''"DS3 share paper upper", "DS3 share paper lower", "names check"])''')
rep('''d["lit"][0], d["lit"][1], d["sep"]])''', '''d["lit"][0], d["lit"][1], d["names"]])''')
rep('''    w = np.array(r.W["both"], float)[np.ix_(keep, keep)]''', '''    w = np.array(r.W["both"], float)[np.ix_(keep, keep)]''')
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
