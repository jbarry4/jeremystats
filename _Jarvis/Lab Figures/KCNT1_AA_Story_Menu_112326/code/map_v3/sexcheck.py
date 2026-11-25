"""Whole-colony sex check: KCNT1 Archive vs Active 2.0 vs SoftMouse vs VOS (all cards Jarvis kept)."""
import openpyxl, os, re, json, glob, collections, csv
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = r"C:\Users\Z390\Desktop\jeremystats"
wb = openpyxl.load_workbook(os.path.join(HERE, "labops_1623.xlsx"), data_only=True)


def mid(v):
    s = str(v or "").strip().replace(".0", "")
    m = re.match(r"^(\d+)", s)
    return str(int(m.group(1))) if m else None


def sexn(v):
    s = str(v or "").strip().upper().rstrip("?")
    return {"FEMALE": "F", "MALE": "M"}.get(s, s) if s in ("M", "F", "MALE", "FEMALE") else None


def tab(name, idname, sexname="Sex"):
    ws = wb[name]
    h = [c.value for c in ws[1]]
    out = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        m = mid(r[h.index(idname)])
        if m and sexn(r[h.index(sexname)]):
            out.setdefault(m, sexn(r[h.index(sexname)]))
    return out


ARC = tab("KCNT1 Archive", "Mouse")
V1 = tab("KCNT1 Active (Archived)", "Mouse ID")
V2 = tab("KCNT1 Active 2.0", "Mouse ID")
SM = {}
for x in json.load(open(os.path.join(HERE, "softmouse_list.json"), encoding="utf-8")):
    t = re.sub(r"\D", "", re.sub(r"<[^>]+>", " ", str(x.get("physicaltag") or "")))
    if t and sexn(x.get("sex")):
        SM[str(int(t))] = sexn(x.get("sex"))
VOS = collections.defaultdict(set)
for f in glob.glob(os.path.join(REPO, "Colony Management", "VOS Exports", "Jarvis", "syncs", "*.json")):
    for r in json.load(open(f, encoding="utf-8")).get("census") or []:
        m = mid(r[0])
        if m and sexn(r[3]):
            VOS[m].add(sexn(r[3]))
VOS = {m: next(iter(s)) for m, s in VOS.items() if len(s) == 1}
json.dump(dict(ARC=ARC, V1=V1, V2=V2, SM=SM, VOS=VOS), open(os.path.join(HERE, "sexsrc.json"), "w"), indent=0)

print("sizes", {k: len(v) for k, v in dict(ARC=ARC, V1=V1, V2=V2, SM=SM, VOS=VOS).items()})
for a, b in [("ARC", "V2"), ("ARC", "SM"), ("V2", "SM"), ("V2", "VOS"), ("SM", "VOS"), ("ARC", "VOS"), ("V1", "V2")]:
    A, B = locals()[a], locals()[b]
    both = [m for m in A if m in B]
    dis = sorted([m for m in both if A[m] != B[m]], key=int)
    print("%-4s vs %-4s  both %3d  disagree %3d  %s" % (a, b, len(both), len(dis), dis))
# for the V2-vs-SM disagreements, who else is on which side
print()
rows = []
for m in sorted(set(V2) | set(SM), key=int):
    vals = {k: d.get(m) for k, d in dict(ARC=ARC, V1=V1, V2=V2, SM=SM, VOS=VOS).items()}
    present = {k: v for k, v in vals.items() if v}
    if len(set(present.values())) > 1:
        rows.append((m, present))
        print(m, present)
print("mice with any disagreement:", len(rows))
