"""Gather every source's word on sex / YH / Cre / DOB / AA dates per mouse -> sources.json"""
import os, re, json, csv, glob, datetime, collections
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = r"C:\Users\Z390\Desktop\jeremystats"
AA = os.path.join(REPO, "KCNT1 Active Avoidance", "DATA AND ARCHIVE")
CS = os.path.join(os.environ["LOCALAPPDATA"], "Jarvis", "chickenscratch")

src = collections.defaultdict(lambda: collections.defaultdict(list))   # mouse -> field -> [(source, value)]
notes = collections.defaultdict(list)                                    # mouse -> [(source, text)]
aa_dates = collections.defaultdict(list)                                 # mouse -> [(source, text)]


def d2s(v):
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d")
    return v


def mid(v):
    s = str(v or "").strip()
    s = s.split(".")[0] if re.fullmatch(r"\d+\.0", s) else s
    s = re.sub(r"^[Mm]", "", s)
    return s if s.isdigit() else None


def add(m, field, source, value):
    if value is None:
        return
    v = str(d2s(value)).strip()
    if v == "" or v.lower() in ("none", "n/a?"):
        return
    src[m][field].append((source, v))


# --- Lab Operations Schedule (live export) ---------------------------------------------------
wb = openpyxl.load_workbook(os.path.join(HERE, "labops.xlsx"), data_only=True)
for tab, label in [("KCNT1 Active 2.0", "Lab Ops: KCNT1 Active 2.0"),
                   ("KCNT1 Active (Archived)", "Lab Ops: KCNT1 Active (Archived)"),
                   ("KCNT1 Archive", "Lab Ops: KCNT1 Archive")]:
    ws = wb[tab]
    hdr = [c.value for c in ws[1]]
    idc = hdr.index("Mouse ID") if "Mouse ID" in hdr else hdr.index("Mouse")
    col = {h: i for i, h in reversed(list(enumerate(hdr))) if h}
    aa_cols = [i for i, h in enumerate(hdr) if h and str(h).startswith("Active avoidance")]
    for row in ws.iter_rows(min_row=2):
        m = mid(row[idc].value)
        if not m:
            continue
        for f in ("Sex", "YH", "SST", "PV", "DOB"):
            if f in col:
                add(m, f, label, row[col[f]].value)
        for i in aa_cols:
            v = row[i].value
            if v not in (None, ""):
                aa_dates[m].append((label + " / " + hdr[i], str(d2s(v))))
            if row[i].comment is not None:
                notes[m].append((label + " cell note on " + hdr[i], row[i].comment.text.strip()))
        if "Notes" in col:
            n = row[col["Notes"]].value
            if n and re.search(r"avoid|\bAA\b|pacer|habituat", str(n), re.I):
                notes[m].append((label + " Notes", str(n).strip()))

# --- SoftMouse (live list) ---------------------------------------------------------------------
def strip(v):
    return re.sub(r"<[^>]+>", " ", str(v or "")).strip()

for x in json.load(open(os.path.join(HERE, "softmouse_list.json"), encoding="utf-8")):
    m = mid(re.sub(r"\D", "", strip(x.get("physicaltag"))))
    if not m:
        continue
    add(m, "Sex", "SoftMouse", strip(x.get("sex")))
    dob = strip(x.get("dateofbirth"))
    if dob:
        add(m, "DOB", "SoftMouse", datetime.datetime.strptime(dob, "%m-%d-%Y").strftime("%Y-%m-%d"))
    g = strip(x.get("genotype"))
    mm = re.search(r"YH\((\w+)\)", g)
    if mm:
        add(m, "YH", "SoftMouse", mm.group(1))
    for cre in ("SST", "PV"):
        mm = re.search(cre + r"-Cre\((\w+)\)", g)
        if mm:
            add(m, cre, "SoftMouse", mm.group(1))
    src[m]["_softmouse_genotype"].append(("SoftMouse", g))
    end = strip(x.get("enddate"))
    if end:
        src[m]["_end"].append(("SoftMouse", end + " " + strip(x.get("endtype"))))
    c = strip(x.get("comment"))
    if c and re.search(r"avoid|\bAA\b|pacer", c, re.I):
        notes[m].append(("SoftMouse comment", c))

# --- VOS (every census Jarvis kept, and the parsed VOS reports) -------------------------------
for f in sorted(glob.glob(os.path.join(REPO, "Colony Management", "VOS Exports", "Jarvis", "syncs", "*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    for r in d.get("census") or []:
        m = mid(r[0])
        if not m:
            continue
        if r[2] and re.match(r"\d{4}-\d\d-\d\d$", r[2]):
            add(m, "DOB", "VOS", r[2])
        if r[3]:
            add(m, "Sex", "VOS", r[3])
for f in sorted(glob.glob(os.path.join(REPO, "Colony Management", "VOS Exports", "VOS Report to CSV", "*.csv"))):
    for r in csv.DictReader(open(f, encoding="utf-8-sig", errors="replace")):
        m = mid(r.get("Extracted Sorting ID"))
        if not m:
            continue
        dob = (r.get("DOB") or "").strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                add(m, "DOB", "VOS", datetime.datetime.strptime(dob, fmt).strftime("%Y-%m-%d"))
                break
            except ValueError:
                pass
        if r.get("Sex"):
            add(m, "Sex", "VOS", r["Sex"])

# --- the AA outputs workbook (2024 + 2026 thru June) --------------------------------------------
wbA = openpyxl.load_workbook(os.path.join(AA, "KCNT1_AA_2024_thru_June26_outputs.xlsx"), data_only=True)
book_files = {}
for r in wbA["2024 + 2026 data"].iter_rows(min_row=2, values_only=True):
    fn = (r[0] or "").strip()
    if not fn:
        continue
    book_files[fn] = dict(mouse=str(r[1]), session=str(r[5]), day=r[6])
    m = str(r[1])
    add(m, "Sex", "AA outputs workbook", r[2])
    add(m, "YH", "AA outputs workbook", r[4])
    src[m]["_book_age"].append(("AA outputs workbook", str(r[3])))
for r in wbA["groups by genotype"].iter_rows(min_row=2, values_only=True):
    if r[0]:
        m = str(r[0])
        add(m, "SST", "AA outputs workbook", r[3])
        add(m, "PV", "AA outputs workbook", r[4])

# --- Chicken Scratch facts (Drive sheets, notebooks), minus what was read live above ------------
LIVE = ("Lab Operations Schedule / KCNT1 Active 2.0", "Lab Operations Schedule / KCNT1 Active (Archived",
        "Lab Operations Schedule / KCNT1 Archive", "SoftMouse.NET", "VOS census")
F = json.load(open(os.path.join(CS, "facts_all.json"), encoding="utf-8"))
for f in F.values():
    if f["project"] != "KCNT1" or not f["raw"] or not str(f["raw"]).isdigit():
        continue
    if f["source"].startswith(LIVE):
        continue
    m = str(int(f["raw"]))
    s = re.sub(r"^Barry ECD Lab Drive/", "Drive: ", f["source"])
    s = re.sub(r" / Sheet\d+$", "", s)
    v = str(f["value"])
    if f["type"] == "genotype":
        for gene, pat in (("YH", r"\bYH\s*[=(]\s*(\w+)"), ("YH", r"\bGeno\s*=\s*(\w+)"),("SST", r"\bSST(?:-Cre)?\s*[=(]\s*(\w+)"),
                          ("PV", r"\bPV(?:-Cre)?\s*[=(]\s*(\w+)")):
            mm = re.search(pat, v)
            if mm:
                add(m, gene, s, mm.group(1))
    elif f["type"] == "sex":
        mm = re.search(r"([MF]\??)$", v.strip(), re.I)
        if mm:
            add(m, "Sex", s, mm.group(1))
    elif f["type"] == "dob" and f.get("date"):
        add(m, "DOB", s, f["date"])
    elif f["type"] == "behavior" and re.search(r"avoid|\bAA\b", v, re.I):
        aa_dates[m].append((s, v + ((" (" + f["date"] + ")") if f.get("date") else "")))
        if "Behaviour" in s:
            notes[m].append((s, v))
    elif f["type"] == "note" and re.search(r"avoid|\bAA\b|pacer", v + " " + str(f.get("detail") or ""), re.I):
        t = (v + (": " + f["detail"] if f.get("detail") else "")).strip()
        notes[m].append((s, t))

json.dump(dict(src=src, notes=notes, aa_dates=aa_dates, book_files=book_files),
          open(os.path.join(HERE, "sources.json"), "w", encoding="utf-8"), indent=1, default=str)
print("mice with any record:", len(src))
