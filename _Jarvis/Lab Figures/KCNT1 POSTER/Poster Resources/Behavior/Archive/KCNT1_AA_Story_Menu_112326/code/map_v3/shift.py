"""Was v1 (KCNT1 Active (Archived)) built from KCNT1 Archive with a row offset? Test sex and notes."""
import openpyxl, os, re, collections
HERE = os.path.dirname(os.path.abspath(__file__))
wb = openpyxl.load_workbook(os.path.join(HERE, "labops_1623.xlsx"), data_only=True)


def mid(v):
    s = str(v or "").strip()
    m = re.match(r"^(\d+)", s.replace(".0", ""))
    return m.group(1) if m else None


def sexn(v):
    s = str(v or "").strip().upper().rstrip("?")
    return s if s in ("M", "F") else None


arc = wb["KCNT1 Archive"]
ah = [c.value for c in arc[1]]
arows = [r for r in arc.iter_rows(min_row=2, values_only=True)]
a_order = [(mid(r[2]), sexn(r[3]), r) for r in arows]
a_sex = {m: s for m, s, _ in a_order if m}
a_idx = {m: i for i, (m, s, _) in enumerate(a_order) if m}

for tab in ["KCNT1 Active (Archived)", "KCNT1 Active 2.0"]:
    ws = wb[tab]
    h = [c.value for c in ws[1]]
    sc = h.index("Sex")
    v_rows = [(mid(r[0]), sexn(r[sc])) for r in ws.iter_rows(min_row=2, values_only=True)]
    agree = dis = 0
    disl = []
    for m, s in v_rows:
        if m in a_sex and a_sex[m] and s:
            if a_sex[m] == s:
                agree += 1
            else:
                dis += 1
                disl.append(m)
    print("==", tab, "agree", agree, "disagree", dis, disl)
    # offset test: for disagreeing mice, does v1 sex match the archive neighbor's sex?
    for off in (-2, -1, 1, 2):
        hits = 0
        for m in disl:
            i = a_idx[m] + off
            if 0 <= i < len(a_order) and a_order[i][1] == dict(v_rows).get(m):
                hits += 1
        print("   offset", off, "explains", hits, "of", len(disl))
# where are the disagreeing mice in the archive? print archive neighborhood
dis = ["414", "416", "448", "464", "477", "479", "482", "526", "527", "814", "872", "894"]
v1 = wb["KCNT1 Active (Archived)"]
vh = [c.value for c in v1[1]]
v1sex = {mid(r[0]): sexn(r[vh.index("Sex")]) for r in v1.iter_rows(min_row=2, values_only=True)}
print("archive order (row, mouse, archive sex, v1 sex):")
for i, (m, s, r) in enumerate(a_order):
    if m:
        flag = " <-- differs" if v1sex.get(m) and s and v1sex.get(m) != s else ""
        print("  ", i + 2, m, s, v1sex.get(m), flag)
