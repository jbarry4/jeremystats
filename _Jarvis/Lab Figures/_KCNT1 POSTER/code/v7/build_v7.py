"""KCNT1 poster v7 = v4's deck with v7's figures and the user's comments on v6:
  header     a third shorter: smaller logos, 54 pt title, the affiliations on two lines
  type       Aptos everywhere (Aptos Display for the title and the section headings), in the figures too
  panels     panel letters in UVM-gold badges, panel headings in the poster's green (no gold text on white)
  funding    as on the PTEN poster (PTEN Research, NIH R21-NS133670-02 and R01-MH134787-02), its logos in white on green
  figures    the lab's cells on every depth profile and in the dentate circuit, a 2 x 2 f-I matrix, a drawn micromanipulator,
             both blades in the laminar recording, CSD + voltage and voltage-over-spectrogram, a sharper IED, figure E's
             stages lined up with its clock, crisp atlas sections, the light's pulses in figure F
usage: python build_v7.py V4.pptx OUTDIR_OF_PNGS OUT.pptx"""
import copy, os, re, shutil, sys, zipfile
from lxml import etree
from PIL import Image

SRC, PNG, OUT = sys.argv[1:4]
W = OUT + ".unpacked"
shutil.rmtree(W, ignore_errors=True)
with zipfile.ZipFile(SRC) as z:
    z.extractall(W)
EMU = 914400
NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main", "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships", "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
A, Pn, R = NS["a"], NS["p"], NS["r"]
sp, rp = os.path.join(W, "ppt/slides/slide1.xml"), os.path.join(W, "ppt/slides/_rels/slide1.xml.rels")
t, rels = etree.parse(sp), etree.parse(rp)
TREE = t.find(".//p:cSld/p:spTree", NS)
el = lambda i: t.xpath("//p:cNvPr[@id='%d']/ancestor::*[self::p:sp or self::p:pic][1]" % i, namespaces=NS)[0]   # noqa: E731
E = lambda v: str(int(round(v * EMU)))   # noqa: E731
NEXT_ID = [max(int(c.get("id")) for c in t.iter("{%s}cNvPr" % Pn)) + 1]
GREEN, GOLD, DARK, INK = "154734", "FFD416", "0B2A1F", "1E1E1E"
BODY, HEAD = "Aptos", "Aptos Display"


def new_id():
    NEXT_ID[0] += 1
    return NEXT_ID[0]


def place(i, x=None, y=None, w=None, h=None):
    x_ = el(i).find(".//a:xfrm", NS)
    o, s = x_.find("a:off", NS), x_.find("a:ext", NS)
    for node, k, v in ((o, "x", x), (o, "y", y), (s, "cx", w), (s, "cy", h)):
        if v is not None:
            node.set(k, E(v))


def _drop_media(rid):
    rel = rels.xpath("//pr:Relationship[@Id='%s']" % rid, namespaces=NS)[0]
    users = [r for r in rels.xpath("//pr:Relationship", namespaces=NS) if r.get("Target") == rel.get("Target")]
    path = os.path.normpath(os.path.join(W, "ppt", "slides", rel.get("Target")))
    return rel, users, path


def picture(i, png, x, y, w):
    pic = el(i)
    blip = pic.find(".//a:blip", NS)
    rel, users, old = _drop_media(blip.get("{%s}embed" % R))
    name = "image_v7_" + os.path.basename(png)
    shutil.copy2(png, os.path.join(W, "ppt", "media", name))
    rel.set("Target", "../media/" + name)
    if len(users) == 1 and os.path.exists(old):
        os.remove(old)
    for src in pic.findall(".//a:srcRect", NS):
        src.getparent().remove(src)
    with Image.open(png) as im:
        h = w * im.height / im.width
    place(i, x, y, w, h)
    return h


def delete(i):
    e = el(i)
    blip = e.find(".//a:blip", NS)
    if blip is not None:
        rel, users, path = _drop_media(blip.get("{%s}embed" % R))
        rel.getparent().remove(rel)
        if len(users) == 1 and os.path.exists(path):
            os.remove(path)
    e.getparent().remove(e)


def texts(i, new):
    runs = el(i).xpath(".//a:r", namespaces=NS)
    assert len(runs) == len(new), (i, len(runs), [r.find("a:t", NS).text for r in runs])
    for r, s in zip(runs, new):
        r.find("a:t", NS).text = s


def para_runs(i, k, new):
    p = el(i).xpath(".//a:p", namespaces=NS)[k]
    runs = p.xpath("./a:r", namespaces=NS)
    assert len(runs) == len(new), (i, k, [r.find("a:t", NS).text for r in runs])
    for r, s in zip(runs, new):
        r.find("a:t", NS).text = s


def size(i, pt):
    for rp_ in el(i).iter("{%s}rPr" % A, "{%s}endParaRPr" % A):
        rp_.set("sz", str(int(round(pt * 100))))


def color(i, hexv):
    for rp_ in el(i).iter("{%s}rPr" % A):
        f = rp_.find("a:solidFill", NS)
        if f is not None:
            f.getparent().remove(f)
        sf = etree.SubElement(rp_, "{%s}solidFill" % A)
        etree.SubElement(sf, "{%s}srgbClr" % A, val=hexv)
        rp_.remove(sf)
        rp_.insert(0, sf)


def _rpr(sz, hexv, bold=False, face=BODY, italic=False):
    return ('<a:rPr lang="en-US" sz="%d"%s%s dirty="0"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
            '<a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface="%s"/></a:rPr>' %
            (int(sz * 100), ' b="1"' if bold else "", ' i="1"' if italic else "", hexv, face, BODY, BODY))


def add_shape(name, x, y, w, h, fill=None, geom="rect", radius=None, paras=None, anchor="ctr", algn="ctr", z_after=None, ins=0.0):
    """a new shape (a filled box, a text box, or both); paras = [[(text, size, colour, bold, italic), ...], ...]."""
    i = new_id()
    av = '<a:avLst><a:gd name="adj" fmla="val %d"/></a:avLst>' % radius if radius is not None else "<a:avLst/>"
    fill_x = '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>' % fill if fill else "<a:noFill/>"
    body = ""
    for para in (paras or [[]]):
        runs = "".join("<a:r>%s<a:t>%s</a:t></a:r>" % (_rpr(q[1], q[2], q[3], q[5] if len(q) > 5 else BODY, q[4]),
                                                     (q[0].replace("&", "&amp;").replace("<", "&lt;"))) for q in para)
        body += '<a:p><a:pPr marL="0" indent="0" algn="%s"><a:buNone/></a:pPr>%s</a:p>' % (algn, runs)
    xml = ('<p:sp xmlns:p="%s" xmlns:a="%s" xmlns:r="%s"><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr%s/><p:nvPr/></p:nvSpPr>'
           '<p:spPr><a:xfrm><a:off x="%s" y="%s"/><a:ext cx="%s" cy="%s"/></a:xfrm><a:prstGeom prst="%s">%s</a:prstGeom>%s<a:ln><a:noFill/></a:ln></p:spPr>'
           '<p:txBody><a:bodyPr wrap="square" lIns="%s" tIns="0" rIns="%s" bIns="0" rtlCol="0" anchor="%s"/><a:lstStyle/>%s</p:txBody></p:sp>'
           % (Pn, A, R, i, name, ' txBox="1"' if not fill else "", E(x), E(y), E(w), E(h), geom, av, fill_x, E(ins), E(ins), anchor, body))
    node = etree.fromstring(xml)
    if z_after is not None:
        el(z_after).addnext(node)
    else:
        TREE.append(node)
    return i


def add_picture(name, png, x, y, w, z_after=None):
    i = new_id()
    media = "image_v7_" + os.path.basename(png)
    shutil.copy2(png, os.path.join(W, "ppt", "media", media))
    ids = [int(r.get("Id")[3:]) for r in rels.getroot() if r.get("Id", "").startswith("rId")]
    rid = "rId%d" % (max(ids) + 1)
    etree.SubElement(rels.getroot(), "{%s}Relationship" % NS["pr"], Id=rid,
                     Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image", Target="../media/" + media)
    with Image.open(png) as im:
        h = w * im.height / im.width
    xml = ('<p:pic xmlns:p="%s" xmlns:a="%s" xmlns:r="%s"><p:nvPicPr><p:cNvPr id="%d" name="%s" descr="%s"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/>'
           '</p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
           '<p:spPr><a:xfrm><a:off x="%s" y="%s"/><a:ext cx="%s" cy="%s"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
           % (Pn, A, R, i, name, name, rid, E(x), E(y), E(w), E(h)))
    node = etree.fromstring(xml)
    (el(z_after).addnext(node) if z_after is not None else TREE.append(node))
    return i, h


def subheading(i, x, y, w, h, sz=None):
    """the panel letter out of the text and into a UVM-gold badge; the heading itself in the poster's green."""
    run = el(i).xpath(".//a:r", namespaces=NS)[0]
    tx = run.find("a:t", NS).text
    m = re.match(r"^([A-Z])\s+(.*)$", tx, re.S)
    letter, rest = m.group(1), m.group(2)
    run.find("a:t", NS).text = rest
    color(i, GREEN)
    if sz:
        size(i, sz)
    pt = sz or int(run.find("a:rPr", NS).get("sz")) / 100
    bs = 0.5 * pt / 26.0 + 0.02                                  # the badge: as tall as the heading's capitals and a bit
    add_shape("Panel %s badge" % letter, x, y + 0.02, bs, bs, fill=GOLD, geom="roundRect", radius=22000,
              paras=[[(letter, pt * 0.9, GREEN, True, False)]], z_after=i)
    place(i, x + bs + 0.16, y, w - bs - 0.16, h)


P = lambda n: os.path.join(PNG, n)   # noqa: E731
log = []

# ================================================================== type: Aptos everywhere, Aptos Display for the big lines
HEADS = {6, 11, 21, 33, 45, 51, 61, 67, 71, 77}
for e_ in t.iter("{%s}latin" % A, "{%s}ea" % A, "{%s}cs" % A):
    if e_.get("typeface") == "Calibri":
        e_.set("typeface", BODY)
        for k in ("pitchFamily", "charset"):
            e_.attrib.pop(k, None)
for i in HEADS:
    for e_ in el(i).iter("{%s}latin" % A):
        e_.set("typeface", HEAD)
# the theme too, so anything unstyled follows
th = os.path.join(W, "ppt", "theme")
for f in os.listdir(th):
    p_ = os.path.join(th, f)
    s_ = open(p_, encoding="utf8").read()
    s_ = re.sub(r'(<a:(?:major|minor)Font>\s*<a:latin typeface=")[^"]*(")', lambda m: m.group(1) + (HEAD if "major" in m.group(0) else BODY) + m.group(2), s_)
    open(p_, "w", encoding="utf8").write(s_)

# ================================================================== header: a third shorter
HB = 3.72
place(2, 0, 0, 48.0, HB)
place(3, 0.55, 0.2, 3.5, 3.5 * 2.33 / 5.0)
place(4, 0.55, 0.2 + 3.5 * 2.33 / 5.0 + 0.12, 3.35, 3.35 * 2.55 / 5.2)
place(5, 40.25, 1.12, 7.25, 7.25 * 1.54 / 7.9)
place(6, 4.55, 0.16, 35.2, 1.72); size(6, 54)
place(7, 4.55, 1.96, 35.2, 0.55); size(7, 25)
# affiliations on two lines: 1 and 2 together, then 3
aff = el(8)
ps = aff.findall(".//a:p", NS)
spacer = copy.deepcopy(ps[0].findall("a:r", NS)[1]); spacer.find("a:t", NS).text = "      "
ps[0].append(spacer)
for r_ in ps[1].findall("a:r", NS):
    ps[0].append(r_)
e1 = ps[0].find("a:endParaRPr", NS)
if e1 is not None:
    ps[0].remove(e1); ps[0].append(e1)
ps[1].getparent().remove(ps[1])
place(8, 4.55, 2.56, 35.2, 0.95); size(8, 19)
TOP = HB + 0.42                                    # every card starts here (v6: 6.0)
GAPC = 0.38                                        # between cards in a column

# ================================================================== column 1: introduction
for i in (9, 10, 11):
    place(i, y=TOP)
place(12, 0.9, TOP + 1.3, 13.8, 3.55); size(12, 20)
para_runs(12, 1, ["Homozygous mice carrying a patient variant (", "Kcnt1", " Y777H, human Y796H) have frequent, sleep-related seizures and "
                  "interictal epileptiform discharges (IEDs) that map to motor cortex [3]. The extra K", "+", " current quiets inhibitory "
                  "neurons, not excitatory ones: SST-type interneurons fire less in heterozygous and homozygous mice, while PV-type "
                  "interneurons fire more in heterozygous and less in homozygous mice [3, 4]."])
YF = TOP + 1.3 + 3.55 + 0.1
h = picture(13, P("I_fI.png"), 0.9, YF, 7.4); log.append(("I_fI", h))
place(14, 0.9, YF + h + 0.06, 7.4, 1.15); size(14, 15.5)
texts(14, ["SST", " and ", "PV", "-type interneurons under KCNT1 gain of function, each against its own WT (grey), mean ± SEM, as "
           "printed. Het: SST and PV interneurons (Shore et al., eLife 2024, Fig. 4C, CC BY 4.0). Hom: non-fast-spiking and "
           "fast-spiking cells (Shore et al., Cell Rep 2020, Fig. 4). Redrawn; example traces at one scale."])
hc = picture(15, P("I_circuit.png"), 8.75, YF + 0.04, 5.9); log.append(("I_circuit", hc))
place(16, 8.75, YF + 0.04 + hc + 0.08, 5.9, 2.2); size(16, 15.5)
texts(16, ["Entorhinal input reaches the granule cells' (pink) dendrites: lateral (LEC) in the outer and medial (MEC) in the middle "
           "molecular layer. The hilar SST (HIPP) cell's axon spreads in the outer third, where LEC input lands; the PV basket cell's "
           "axon wraps the granule cells' somata [6]. Granule cells as drawn in the lab's PTEN figure; SST and PV after their real form."])
YH = max(YF + h + 0.06 + 1.15, YF + 0.04 + hc + 0.08 + 2.2) + 0.15
place(17, 0.9, YH, 13.8, 1.2)
place(18, 1.2, YH + 0.04, 13.2, 1.12); size(18, 20)
INTRO_END = YH + 1.2 + 0.2
place(9, h=INTRO_END - TOP)
log.append(("intro card ends", INTRO_END))

# ================================================================== column 1: methods
TOPM = INTRO_END + GAPC
for i in (19, 20, 21):
    place(i, y=TOPM)
place(19, h=35.5 - TOPM)
y = TOPM + 1.32
h1 = picture(22, P("M_headfixed.png"), 0.9, y, 5.0)
h2 = picture(23, P("M_laminar.png"), 6.1, y, 8.6)
log += [("M_headfixed", h1), ("M_laminar", h2)]
y += max(h1, h2) + 0.25
place(24, 0.9, y, 13.8, 1.0); size(24, 16.5)
texts(24, ["Recording. ", "Awake, head-fixed ", "Kcnt1", " Y777H WT, Het and Hom mice on a treadmill. A 64-contact silicon probe spans "
           "CA1 and both dentate blades (right: a control recording, the lab's cells beside its layers); for optogenetics, an optical "
           "fiber sits beside it. Current source density (CSD) maps where current enters cells (sinks, blue) and leaves them (sources, red)."])
y += 1.3
he = picture(25, P("M_events.png"), 0.9, y, 9.6); log.append(("M_events", he))
place(26, 10.72, y + 0.5, 3.98, he - 0.5); size(26, 16)
texts(26, ["Reading the CSD (", "Kcnt1", " m1609, YH Het). ", "A curated dentate spike and IED from one recording, on one depth axis: "
           "the CSD with the voltage over it (one CSD scale and one voltage scale for both), and spectrograms of eight contacts, "
           "each with its own voltage drawn over it. The dentate spike puts brief sinks in both blades with a source between [5]; "
           "the IED is sharp (half-width 12 ms), more than twice as large, runs from CA1 through both blades and carries a burst of "
           "100–600 Hz power."])
y += he + 0.4
hh = picture(27, P("M_histology.png"), 0.9, y, 3.1); log.append(("M_histology", hh))
place(28, 4.2, y + 0.3, 3.8, 2.9); size(28, 16)
texts(28, ["Optogenetics. ", "SST-Cre × ", "Kcnt1", " Y777H mice received Cre-dependent ChR2 (AAV-PHP.eB CAG-DIO-ChR2); the fiber "
           "delivered 5–12 Hz light. Left: SST (green) and NeuN (red) in the dentate, 20x; arrows, two SST cells."])
ha = picture(29, P("M_arena.png"), 8.2, y, 3.1); log.append(("M_arena", ha))
place(30, 11.45, y + 0.3, 3.25, 2.9); size(30, 16)
log.append(("methods bottom row ends", y + max(hh, ha)))

# ================================================================== column 2: behavior
for i in (59, 60, 61):
    place(i, y=TOP)
subheading(62, 15.9, TOP + 1.25, 15.0, 0.6)
h = picture(63, P("A_behavior.png"), 15.9, TOP + 1.95, 15.0); log.append(("A_behavior", h))
place(64, 15.9, TOP + 1.95 + h + 0.12, 15.0, 0.85); size(64, 15)
BEH_END = TOP + 1.95 + h + 0.12 + 0.85 + 0.15
place(59, h=BEH_END - TOP)
# ================================================================== column 2: where discharges start
TOPD = BEH_END + GAPC
for i in (31, 32, 33):
    place(i, y=TOPD)
subheading(34, 15.9, TOPD + 1.25, 15.0, 0.6)
h = picture(35, P("B_ied.png"), 15.9, TOPD + 1.95, 15.0); log.append(("B_ied", h))
yb = TOPD + 1.95 + h
place(36, 15.9, yb + 0.05, 15.0, 0.75); size(36, 15)
texts(36, ["One IED in a KCNT1 mouse (our 2025 poster, redrawn). ", "Left: ", "CSD (sinks blue, sources red) with the LFP of cortex, CA1 "
           "and hilus over it, the lab's cells beside its layers, and the probe track; the first sink is in the hilus, then CA1 and "
           "cortex follow. ", "Right: ", "before the IED, hilar LFP carries β–γ power that CA1 lacks, and hilar units (300–6000 Hz) fire."])
yc = yb + 0.05 + 0.75 + 0.3
subheading(37, 15.9, yc, 10.0, 0.95, sz=24)
para_runs(40, 0, ["D  Under urethane, Hom mice have IEDs; WT rarely do"])
subheading(40, 26.25, yc, 4.65, 0.95, sz=22)
h = picture(38, P("C_ds.png"), 15.9, yc + 1.0, 10.0); log.append(("C_ds", h))
place(39, 15.9, yc + 1.0 + h + 0.05, 10.0, 0.95); size(39, 15)
texts(39, ["Left: ", "a discharge in two steps: a sink at the OML and hilus (1), then 3 ms later sinks at OML and MML together (2) and "
           "a ~600 ms deflection. ", "Right: ", "a KCNT1 dentate spike, larger than in controls, again with OML and MML sinks at once "
           "(its profile in black over phase 2 in grey); a control DS uses one or the other [5]. One CSD scale for both."])
hd = picture(41, P("D_urethane.png"), 26.25, yc + 1.0, 4.6); log.append(("D_urethane", hd))
place(42, 26.25, yc + 1.0 + hd + 0.05, 4.65, 1.8); size(42, 15)
DIS_END = max(yc + 1.0 + h + 0.05 + 0.95, yc + 1.0 + hd + 0.05 + 1.8) + 0.2
place(31, h=DIS_END - TOPD)
log.append(("discharges card ends", DIS_END))
# ================================================================== column 2: acknowledgments, references, funding
FUND_H = 1.6
TOPA = DIS_END + GAPC
ACK_H = 35.5 - FUND_H - 0.3 - TOPA
for (card, band, head, x0) in ((69, 70, 71, 15.5), (75, 76, 77, 23.6)):
    place(card, x0, TOPA, 7.7, ACK_H)
    place(band, x0, TOPA, 7.7, 0.7)
    place(head, x0 + 0.4, TOPA, 6.9, 0.7)
place(72, 15.9, TOPA + 0.85, 7.0, ACK_H - 1.0); size(72, 16)
place(78, 24.0, TOPA + 0.85, 7.0, ACK_H - 1.0); size(78, 16)
delete(74); delete(73)
FY = 35.5 - FUND_H
add_shape("Funding strip", 15.5, FY, 15.8, FUND_H, fill=DARK, geom="rect", z_after=78)
add_shape("Funding heading", 15.9, FY, 3.0, FUND_H, paras=[[("FUNDING", 28, "FFFFFF", True, False, HEAD)]], algn="l", anchor="ctr")
ip, hp_ = add_picture("PTEN Research logo (white)", P("logo_pten_white.png"), 19.2, FY + 0.22, 3.2)
add_picture("NIH logo (white)", P("logo_nih_white.png"), 23.3, FY + 0.3, 1.6)
add_shape("Grant numbers", 25.35, FY, 5.7, FUND_H, paras=[[("NIH R21-NS133670-02", 17, "FFFFFF", False, False)],
                                                          [("NIH R01-MH134787-02", 17, "FFFFFF", False, False)]], algn="l", anchor="ctr")
log.append(("acknowledgments/references cards", ACK_H))

# ================================================================== column 3: seizure
for i in (43, 44, 45):
    place(i, y=TOP)
para_runs(46, 0, ["E  The seizure starts in the hilus, then recruits both blades and CA1, as a hilar interneuron falls silent"])
subheading(46, 32.1, TOP + 1.25, 15.0, 0.95)
h = picture(47, P("E_seizure.png"), 32.1, TOP + 2.25, 15.0); log.append(("E_seizure", h))
place(48, 32.1, TOP + 2.25 + h + 0.06, 15.0, 1.75); size(48, 15)
texts(48, ["Spontaneous seizure in awake Hom mouse 459 (one of the six old Hom in A), on one clock: each stage's panels sit over "
           "its second below (the 3 s before onset on their own, narrower clock). ", "Top: ", "each stage on the atlas section the "
           "probe went down (Allen CCF, AP −1.9 mm), and the CSD (sinks blue, sources red) with the LFP over it; the cells mark "
           "CA1, the upper blade, the hilus and the lower blade. ", "Middle: ", "the hilar interneuron (CSC 41) fired at 58 spikes/s "
           "in the 3 s before onset (4.7× its 12.4 Hz baseline) and in bursts to 2.3 s, then stopped: no spikes 2.6–3.7 s, 0.4/s "
           "after the seizure. ", "Bottom: ", "each zone's |CSD| divided by its own quiet baseline, which is how each stage is "
           "called. In stage 1 the upper blade carries the largest currents (the strongest colour; at rest its |CSD| is 2.5× the "
           "hilus's), but the hilus rises first and most: past 15× at 0.2 s against 0.5 s, and to 59× against 28× at 0.7 s. "
           "One opportunistic seizure."])
SEZ_END = TOP + 2.25 + h + 0.06 + 1.75 + 0.15
place(43, h=SEZ_END - TOP)
log.append(("seizure card ends", SEZ_END))
# ================================================================== column 3: optogenetics
TOPO = SEZ_END + GAPC
for i in (49, 50, 51):
    place(i, y=TOPO)
place(52, y=TOPO + 0.32); place(53, y=TOPO + 0.32)
para_runs(54, 0, ["F  Light drives an SST unit, and its bursts lock to the light, most at 5 Hz"])
subheading(54, 32.1, TOPO + 1.22, 15.0, 0.55)
h = picture(55, P("F_opto.png"), 32.1, TOPO + 1.85, 15.0); log.append(("F_opto", h))
delete(83)
delete(56)
delete(58)
place(57, 32.1, TOPO + 1.85 + h + 0.06, 15.0, 1.15); size(57, 15)
texts(57, ["One light-driven SST interneuron, one column per condition: the light (one blue tick per pulse), 9 s of raw LFP, its "
           "spectrogram and the unit's spikes, then the unit's spike autocorrelation, scaled to its peak (blue marks: one light "
           "period apart). Right: firing rate and rhythm power at the light frequency, every run (two runs at 5 and 10 Hz). ",
           "Kcnt1", " Y777H mouse with ChR2 in SST cells, H3 probe; redrawn from the numbers in our 2024 poster. Light order: "
           "rest, 10, rest, 10, 5, 7, 12, 5 Hz."])
OPTO_END = TOPO + 1.85 + h + 0.06 + 1.15 + 0.15
place(49, h=OPTO_END - TOPO)
log.append(("opto card ends", OPTO_END))
# ================================================================== column 3: conclusions
TOPC = OPTO_END + GAPC
for i in (65, 66, 67):
    place(i, y=TOPC)
place(65, h=35.5 - TOPC)
place(68, 32.1, TOPC + 1.05, 15.0, 35.5 - TOPC - 1.2); size(68, 21)
para_runs(68, 2, ["3. Hilar inhibition gives way first. ", "A hilar interneuron fired at nearly 5× its baseline in the 3 s before "
                  "onset, then fell silent as the seizure spread."])
log.append(("conclusions card", 35.5 - TOPC))

t.write(sp, xml_declaration=True, encoding="UTF-8", standalone=True)
rels.write(rp, xml_declaration=True, encoding="UTF-8", standalone=True)
if os.path.exists(OUT):
    os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join(W, "[Content_Types].xml"), "[Content_Types].xml")
    for root, _d, fs in os.walk(W):
        for f in fs:
            a_ = os.path.relpath(os.path.join(root, f), W).replace(os.sep, "/")
            if a_ != "[Content_Types].xml":
                z.write(os.path.join(root, f), a_)
shutil.rmtree(W)
for n, hv in log:
    print("%-34s %.2f" % (n, hv))
print("wrote", OUT)
