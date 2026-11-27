"""KCNT1 poster v9 = v4's deck with v9's figures (v8's, answering the comments on v8), and v7's look (Aptos, green panel headings with gold badges, the short
header, funding as on the PTEN poster) laid out on one spacing grid:
  - every figure is trimmed to its ink and placed at its own print size (300 px per inch), so its edges are where the
    layout says and its type is the type it was drawn with
  - every text box is as tall as its text, as PowerPoint itself measures it (tools/measure_text.ps1 on the last build:
    pass MEASURE.json; without it the build estimates)
  - the same gaps everywhere: card top to first item, heading to figure, figure to caption, section to section, last item
    to card bottom, card to card; columns start and end on the same lines
  - panel letters' badges centred on their heading's capitals
usage: python build_v9.py V4.pptx OUTDIR_OF_PNGS OUT.pptx [MEASURE.json]"""
import copy, json, os, re, shutil, sys, zipfile
import numpy as np
from lxml import etree
from PIL import Image

SRC, PNG, OUT = sys.argv[1:4]
MEAS = {}
if len(sys.argv) > 4 and os.path.exists(sys.argv[4]):
    for r_ in json.load(open(sys.argv[4], encoding="utf-8-sig")):
        MEAS[int(r_["id"])] = r_
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
DPI = 300.0

# ------------------------------------------------------------------ the spacing grid (inches)
TOP, BOTTOM = None, 35.5          # cards start under the header, end at the poster's bottom margin
BAND, BAND_S, BAND_C = 1.1, 0.7, 0.85
PAD_TOP, PAD_BOTTOM = 0.24, 0.26  # heading band to first item; last item to the card's bottom
G_HEAD = 0.14                     # panel heading to its figure
G_CAP = 0.1                       # figure to caption
G_SECTION = 0.36                  # caption to the next panel heading, inside a card
G_CARD = 0.38                     # card to card
G_TEXT = 0.2                      # a block of text to the figure under it
L1, R1 = 0.9, 14.7                # the three columns' content edges
L2, R2 = 15.9, 30.9
L3, R3 = 32.1, 47.1


def new_id():
    NEXT_ID[0] += 1
    return NEXT_ID[0]


def place(i, x=None, y=None, w=None, h=None):
    x_ = el(i).find(".//a:xfrm", NS)
    o, s = x_.find("a:off", NS), x_.find("a:ext", NS)
    for node, k, v in ((o, "x", x), (o, "y", y), (s, "cx", w), (s, "cy", h)):
        if v is not None:
            node.set(k, E(v))


def th(i, est):
    """a text box's real text height: PowerPoint's own measure of the last build, else an estimate."""
    r_ = MEAS.get(i)
    return float(r_["text_height"]) if r_ else est


def _drop_media(rid):
    rel = rels.xpath("//pr:Relationship[@Id='%s']" % rid, namespaces=NS)[0]
    users = [r for r in rels.xpath("//pr:Relationship", namespaces=NS) if r.get("Target") == rel.get("Target")]
    path = os.path.normpath(os.path.join(W, "ppt", "slides", rel.get("Target")))
    return rel, users, path


TRIM = os.path.join(W, "_trim")
os.makedirs(TRIM, exist_ok=True)


def trimmed(png, pad=5):
    """the figure cropped to its ink (anything not white), a few pixels of margin kept."""
    im = Image.open(png)
    rgba = im.convert("RGBA")
    flat = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), rgba).convert("RGB")
    a = np.asarray(flat)
    ys, xs = np.nonzero((a < 247).any(2))
    box = (max(int(xs.min()) - pad, 0), max(int(ys.min()) - pad, 0), min(int(xs.max()) + pad + 1, im.width), min(int(ys.max()) + pad + 1, im.height))
    out = os.path.join(TRIM, os.path.basename(png))
    im.crop(box).save(out, dpi=(DPI, DPI))
    return out


def picture(i, png, x, y, trim=True):
    """place a figure at its own print size (300 px per inch); returns its (width, height) in inches."""
    src = trimmed(png) if trim else png
    pic = el(i)
    blip = pic.find(".//a:blip", NS)
    rel, users, old = _drop_media(blip.get("{%s}embed" % R))
    name = "image_v9_" + os.path.basename(png)
    shutil.copy2(src, os.path.join(W, "ppt", "media", name))
    rel.set("Target", "../media/" + name)
    if len(users) == 1 and os.path.exists(old):
        os.remove(old)
    for s_ in pic.findall(".//a:srcRect", NS):
        s_.getparent().remove(s_)
    with Image.open(src) as im:
        w, h = im.width / DPI, im.height / DPI
    place(i, x, y, w, h)
    return w, h


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


def space_after(i, pt):
    for p in el(i).iter("{%s}pPr" % A):
        s_ = p.find("a:spcAft", NS)
        if s_ is None:
            s_ = etree.Element("{%s}spcAft" % A)
            p.insert(0, s_)
        for c in list(s_):
            s_.remove(c)
        etree.SubElement(s_, "{%s}spcPts" % A, val=str(int(pt * 100)))


def color(i, hexv):
    for rp_ in el(i).iter("{%s}rPr" % A):
        f = rp_.find("a:solidFill", NS)
        if f is not None:
            f.getparent().remove(f)
        sf = etree.Element("{%s}solidFill" % A)
        etree.SubElement(sf, "{%s}srgbClr" % A, val=hexv)
        rp_.insert(0, sf)


def _rpr(sz, hexv, bold=False, face=BODY, italic=False):
    return ('<a:rPr lang="en-US" sz="%d"%s%s dirty="0"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
            '<a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface="%s"/></a:rPr>' %
            (int(sz * 100), ' b="1"' if bold else "", ' i="1"' if italic else "", hexv, face, BODY, BODY))


def add_shape(name, x, y, w, h, fill=None, geom="rect", radius=None, paras=None, anchor="ctr", algn="ctr", z_after=None, ins=0.0):
    """a new shape (a filled box, a text box, or both); paras = [[(text, size, colour, bold, italic[, face]), ...], ...]."""
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
    media = "image_v9_" + os.path.basename(png)
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


def subheading(i, x, y, w, sz):
    """the panel letter out of the text and into a UVM-gold badge centred on the heading's capitals; the heading in the
    poster's green. Returns the heading's height (measured)."""
    run = el(i).xpath(".//a:r", namespaces=NS)[0]
    tx = run.find("a:t", NS).text
    m = re.match(r"^([A-Z])\s+(.*)$", tx, re.S)
    letter, rest = m.group(1), m.group(2)
    run.find("a:t", NS).text = rest
    color(i, GREEN)
    size(i, sz)
    bs = 0.5 * sz / 26.0 + 0.02                                    # the badge: a little taller than the capitals
    cap_mid = 0.216 * sz / 26.0                                    # Aptos Bold: capitals' middle this far below the line's top
    add_shape("Panel %s badge" % letter, x, y + cap_mid - bs / 2, bs, bs, fill=GOLD, geom="roundRect", radius=22000,
              paras=[[(letter, sz * 0.9, GREEN, True, False)]], z_after=i)
    h = th(i, 0.43 * sz / 26.0)
    place(i, x + bs + 0.16, y, w - bs - 0.16, h + 0.02)
    return h


def break_after(i, marker):
    """a line break right after `marker` in shape i's text, so a two-line heading breaks where its sense does."""
    for r in el(i).xpath(".//a:r", namespaces=NS):
        t_ = r.find("a:t", NS)
        if t_.text and marker in t_.text:
            a, b = t_.text.split(marker, 1)
            t_.text = a + marker.rstrip()
            r2 = copy.deepcopy(r)
            r2.find("a:t", NS).text = b.lstrip()
            br = etree.Element("{%s}br" % A)
            rp2 = r.find("a:rPr", NS)
            if rp2 is not None:
                br.append(copy.deepcopy(rp2))
            r.addnext(br)
            br.addnext(r2)
            return
    raise KeyError(marker)


def card(ids, y, h):
    """a card (its box, heading band and heading) from y, h tall."""
    box, band, head = ids
    place(box, y=y, h=h)
    place(band, y=y)
    place(head, y=y)


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
th_dir = os.path.join(W, "ppt", "theme")
for f in os.listdir(th_dir):
    p_ = os.path.join(th_dir, f)
    s_ = open(p_, encoding="utf8").read()
    s_ = re.sub(r'(<a:(?:major|minor)Font>\s*<a:latin typeface=")[^"]*(")', lambda m: m.group(1) + (HEAD if "major" in m.group(0) else BODY) + m.group(2), s_)
    open(p_, "w", encoding="utf8").write(s_)

# ================================================================== header: the text block centred in the band
HB = 3.72
place(2, 0, 0, 48.0, HB)
lh1 = 3.5 * 2.33 / 5.0
lh2 = 3.35 * 2.55 / 5.2
y0 = (HB - (lh1 + 0.12 + lh2)) / 2
place(3, 0.55, y0, 3.5, lh1)
place(4, 0.55, y0 + lh1 + 0.12, 3.35, lh2)
place(5, 40.25, (HB - 7.25 * 1.54 / 7.9) / 2, 7.25, 7.25 * 1.54 / 7.9)
size(6, 54); size(7, 25); size(8, 19)
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
h6, h7, h8 = th(6, 1.8), th(7, 0.42), th(8, 0.63)
block = h6 + 0.1 + h7 + 0.12 + h8
yh = (HB - block) / 2
place(6, 4.55, yh, 35.2, h6)
place(7, 4.55, yh + h6 + 0.1, 35.2, h7)
place(8, 4.55, yh + h6 + 0.1 + h7 + 0.12, 35.2, h8)
TOP = HB + 0.42

# ================================================================== column 1: introduction (v8: less text, more figure)
y = TOP + BAND + PAD_TOP
size(12, 20)
space_after(12, 5)
para_runs(12, 0, ["KCNT1", " gain-of-function variants in the sodium-activated K", "Na", "1.1 (Slack) channel cause severe "
                  "developmental and epileptic encephalopathies that rarely respond to drugs [1, 2]."])
para_runs(12, 1, ["Mice homozygous for a patient variant (", "Kcnt1", " Y777H) have frequent seizures and interictal discharges (IEDs) [3]. "
                  "The extra K", "+", " current quiets interneurons: SST-type cells fire less, PV-type more in Het "
                  "and less in Hom (left) [3, 4]."])
para_runs(12, 2, ["The hippocampus has been left out of this picture. We recorded the dentate gyrus, where hilar SST interneurons "
                  "gate entorhinal input (right) [6]."])
h12 = th(12, 2.0)
place(12, L1, y, R1 - L1, h12 + 0.02)
y += h12 + G_TEXT
YF = y
wf, hf = picture(13, P("I_fI.png"), L1, YF)
size(14, 15.5)
texts(14, ["SST", " and ", "PV", "-type interneurons under KCNT1 gain of function, each against its own WT (grey), mean ± SEM, as "
           "printed. Het: SST and PV interneurons (Shore et al., eLife 2024, Fig. 4C, CC BY 4.0). Hom: non-fast-spiking and "
           "fast-spiking cells (Shore et al., Cell Rep 2020, Fig. 4). Redrawn; example traces at one scale."])
h14 = th(14, 1.0)
place(14, L1, YF + hf + G_CAP, wf, h14 + 0.02)
left_end = YF + hf + G_CAP + h14
wc, hc = picture(15, P("I_circuit.png"), R1 - 5.86, YF)
XC = R1 - wc
place(15, x=XC)
size(16, 15.5)
texts(16, ["Entorhinal input lands on the granule cells' (pink) dendrites: lateral (LEC) in the outer, medial (MEC) in the middle "
           "molecular layer. The hilar SST (HIPP) cell's axon spreads in the outer third, with the LEC input; the PV basket cell's "
           "wraps the granule cells' somata [6]."])
h16 = th(16, 1.3)
place(16, XC, YF + hc + G_CAP, wc, h16 + 0.02)
# the hypothesis, under the circuit it is about
size(18, 18)
texts(18, ["Hypothesis. ", "KCNT1 gain of function weakens hilar SST interneurons, the gate on entorhinal input. With the gate "
           "failing, discharges and seizures start in the hilus and spread, and learning suffers."])
h18 = th(18, 1.5)
HYP_PAD = 0.2
hyp_top = YF + hc + G_CAP + h16 + 0.3
hyp_h = h18 + 2 * HYP_PAD
right_end = hyp_top + hyp_h
# bottoms level: the hypothesis box ends where the f-I caption does, or both columns end at the lower of the two
end_ = max(left_end, right_end)
hyp_top = end_ - hyp_h
place(17, XC, hyp_top, wc, hyp_h)
place(18, XC + 0.22, hyp_top + HYP_PAD, wc - 0.44, h18 + 0.02)
INTRO_END = end_ + PAD_BOTTOM
card((9, 10, 11), TOP, INTRO_END - TOP)
log += [("I_fI", (wf, hf)), ("I_circuit", (wc, hc)), ("intro: f-I column ends", left_end), ("intro: circuit column ends", right_end),
        ("intro card ends", INTRO_END)]

# ================================================================== column 1: methods
TOPM = INTRO_END + G_CARD
y = TOPM + BAND + PAD_TOP
w1, h1 = picture(22, P("M_headfixed.png"), L1, y)
w2, h2 = picture(23, P("M_laminar.png"), R1 - 8.6, y)
place(23, x=R1 - w2)
row1_end = y + max(h1, h2)
size(24, 16.5)
texts(24, ["Recording. ", "Awake, head-fixed ", "Kcnt1", " Y777H WT, Het and Hom mice on a treadmill. A 64-contact silicon probe spans "
           "CA1 and both dentate blades (right: a control recording, the lab's cells beside its layers); for optogenetics, an optical "
           "fiber sits beside it. Current source density (CSD) maps where current enters cells (sinks, blue) and leaves them (sources, red)."])
h24 = th(24, 0.85)
size(26, 16)
texts(26, ["Reading the CSD (", "Kcnt1", " m1609, YH Het). ", "A curated dentate spike and IED from one recording, on one depth axis: "
           "the CSD with the voltage over it (one CSD scale and one voltage scale for both), and spectrograms of eight contacts, "
           "each with its own voltage drawn over it. The dentate spike puts brief sinks in both blades with a source between [5]. "
           "The IED, chosen from all 688 in the recording for prominence, narrowness and high-frequency power, "
           "is sharp (half-width 12 ms), more than twice as large, fills both blades and the hilus at once and carries a burst "
           "of power between 100 and 600 Hz."])
size(28, 16)
texts(28, ["Optogenetics. ", "SST-Cre × ", "Kcnt1", " Y777H mice received Cre-dependent ChR2 (AAV-PHP.eB CAG-DIO-ChR2); the fiber "
           "delivered 5–12 Hz light. Left: SST (green) and NeuN (red) in the dentate, 20x; arrows, two SST cells."])
size(30, 16)
we, he = picture(25, P("M_events.png"), L1, 0)
wh, hh = picture(27, P("M_histology.png"), L1, 0)
wa, ha = picture(29, P("M_arena.png"), L1, 0)
# the recording text sits close under the two figures it describes; what is left of the card is shared out as the two
# gaps between the card's three blocks (each at least the grid's own)
G_NEAR = 0.16
content = (row1_end - y) + G_NEAR + h24 + he + max(hh, ha)
free = (BOTTOM - PAD_BOTTOM) - (y + content)
gap = max(0.3, free / 2.0)
log.append(("methods: gap between blocks", gap))
yy = row1_end + G_NEAR
place(24, L1, yy, R1 - L1, h24 + 0.02)
yy += h24 + gap
place(25, L1, yy)
XT = L1 + we + 0.3
h26 = th(26, 3.4)
place(26, XT, yy + (he - h26) / 2, R1 - XT, h26 + 0.02)                 # the text beside the figure, centred on it
yy += he + gap
place(27, L1, yy)
X28 = L1 + wh + 0.28
place(29, X28 + 3.72, yy)
X30 = X28 + 3.72 + wa + 0.28
h28, h30 = th(28, 1.6), th(30, 1.6)
place(28, X28, yy + 0.32, 3.72 - 0.28, h28 + 0.02)
place(30, X30, yy + 0.32, R1 - X30, h30 + 0.02)
METH_END = BOTTOM
card((19, 20, 21), TOPM, METH_END - TOPM)
log += [("M_headfixed", (w1, h1)), ("M_laminar", (w2, h2)), ("M_events", (we, he)), ("methods last row ends", yy + max(hh, ha))]

# ================================================================== column 2: behavior
y = TOP + BAND + PAD_TOP
hA = subheading(62, L2, y, R2 - L2, 26)
y += hA + G_HEAD
wA, hA_ = picture(63, P("A_behavior.png"), L2, y)
y += hA_ + G_CAP
size(64, 15)
_r64 = el(64).xpath(".//a:r", namespaces=NS)[0].find("a:t", NS)    # v9: the outliers are kept and no longer ringed
assert "All 56 mice (4 robust-rule outliers ringed in c). " in _r64.text
_r64.text = _r64.text.replace("All 56 mice (4 robust-rule outliers ringed in c). ", "All 56 mice. ").replace(
    "P values uncorrected.", "P values uncorrected.")                    # (so the last line is not two words)
h64 = th(64, 0.75)
place(64, L2, y, R2 - L2, h64 + 0.02)
BEH_END = y + h64 + PAD_BOTTOM
card((59, 60, 61), TOP, BEH_END - TOP)
# ================================================================== column 2: where discharges start
TOPD = BEH_END + G_CARD
y = TOPD + BAND + PAD_TOP
hB = subheading(34, L2, y, R2 - L2, 26)
y += hB + G_HEAD
wB, hB_ = picture(35, P("B_ied.png"), L2, y)
y += hB_ + G_CAP
size(36, 15)
texts(36, ["One IED in a KCNT1 mouse (our 2025 poster, redrawn). ", "Left: ", "CSD (sinks blue, sources red) with the LFP of cortex, CA1 "
           "and hilus over it, the lab's cells beside its layers, and the probe track; the first sink is in the hilus, then CA1 and "
           "cortex follow. ", "Right: ", "before the IED, hilar LFP carries β–γ power that CA1 lacks, and hilar units fire."])
h36 = th(36, 0.75)
place(36, L2, y, R2 - L2, h36 + 0.02)
y += h36 + G_SECTION
XD = 26.25
para_runs(40, 0, ["D  Under urethane, Hom mice have IEDs; WT rarely do"])
break_after(37, "spikes;")                                  # two lines that break where the sense does
hC = subheading(37, L2, y, XD - 0.3 - L2, 24)
hD = subheading(40, XD, y, R2 - XD, 22)
y += max(hC, hD) + G_HEAD
wC, hC_ = picture(38, P("C_ds.png"), L2, y)
wD, hD_ = picture(41, P("D_urethane.png"), XD, y)
size(39, 15); size(42, 15)
texts(39, ["Left: ", "a discharge in two steps: a sink at the OML and hilus (1), then 3 ms later sinks at OML and MML together (2) and "
           "a ~600 ms deflection. ", "Right: ", "a KCNT1 dentate spike, larger than in controls, again with OML and MML sinks at once "
           "(its profile in black over phase 2 in grey); a control DS uses one or the other [5]. One CSD scale for both."])
h39, h42 = th(39, 0.75), th(42, 1.25)
place(39, L2, y + hC_ + G_CAP, XD - 0.3 - L2, h39 + 0.02)
place(42, XD, y + hD_ + G_CAP, R2 - XD, h42 + 0.02)
DIS_END = max(y + hC_ + G_CAP + h39, y + hD_ + G_CAP + h42) + PAD_BOTTOM
card((31, 32, 33), TOPD, DIS_END - TOPD)
# ================================================================== column 2: acknowledgments, references, funding
TOPA = DIS_END + G_CARD
size(72, 16); size(78, 16)
h72, h78 = th(72, 1.1), th(78, 0.9)
FUND_H = 1.5
ACK_H = (BOTTOM - FUND_H - G_CARD) - TOPA
for (cid, bid, hid, x0) in ((69, 70, 71, 15.5), (75, 76, 77, 23.6)):
    place(cid, x0, TOPA, 7.7, ACK_H)
    place(bid, x0, TOPA, 7.7, BAND_S)
    place(hid, x0 + 0.4, TOPA, 6.9, BAND_S)
yt = TOPA + BAND_S + (ACK_H - BAND_S - max(h72, h78)) / 2                    # both texts centred in what is left of their cards
place(72, L2, yt, 7.0, h72 + 0.02)
place(78, 24.0, yt, 7.0, h78 + 0.02)
delete(74); delete(73)
FY = BOTTOM - FUND_H
add_shape("Funding strip", 15.5, FY, 15.8, FUND_H, fill=DARK, geom="rect", z_after=78)
add_shape("Funding heading", L2, FY, 3.0, FUND_H, paras=[[("FUNDING", 28, "FFFFFF", True, False, HEAD)]], algn="l", anchor="ctr")
lw_p, lw_n = 3.15, 1.55
with Image.open(P("logo_pten_white.png")) as im_:
    lh_p = lw_p * im_.height / im_.width
with Image.open(P("logo_nih_white.png")) as im_:
    lh_n = lw_n * im_.height / im_.width
add_picture("PTEN Research logo (white)", P("logo_pten_white.png"), 19.15, FY + (FUND_H - lh_p) / 2, lw_p)
add_picture("NIH logo (white)", P("logo_nih_white.png"), 23.2, FY + (FUND_H - lh_n) / 2, lw_n)
add_shape("Grant numbers", 25.2, FY, R2 - 25.2, FUND_H, paras=[[("NIH R21-NS133670-02", 17, "FFFFFF", False, False)],
                                                              [("NIH R01-MH134787-02", 17, "FFFFFF", False, False)]], algn="l", anchor="ctr")
log += [("discharges card ends", DIS_END), ("ack/ref cards tall", ACK_H)]

# ================================================================== column 3: seizure
y = TOP + BAND + PAD_TOP
para_runs(46, 0, ["E  The seizure starts in the hilus, then recruits both blades and CA1, as a hilar interneuron falls silent"])
break_after(46, "and CA1,")                                 # two balanced lines, not one long line and two words
hE = subheading(46, L3, y, R3 - L3, 26)
y += hE + G_HEAD
wE, hE_ = picture(47, P("E_seizure.png"), L3, y)
y += hE_ + G_CAP
size(48, 15)
texts(48, ["Spontaneous seizure in awake Hom mouse 459 (one of the six old Hom in A), on one clock: each stage's panels sit over "
           "its second below (the 3 s before onset on their own, narrower clock). ", "Top: ", "each stage on the atlas section the "
           "probe went down (Allen CCF, AP −1.9 mm), and the CSD (sinks blue, sources red) with the LFP over it; the cells mark "
           "CA1, both blades (a PV basket cell at each granule layer) and the hilus (an SST cell, its axon in both outer molecular "
           "layers). ", "Middle: ", "the hilar interneuron (CSC 41) "
           "fired at 58 spikes/s in the 3 s before onset (4.7× its 12.4 Hz baseline) and in bursts to 2.3 s, then stopped: no spikes "
           "2.6–3.7 s, 0.4/s after the seizure. ", "Bottom: ", "each zone's |CSD| divided by its own quiet baseline, which is how each "
           "stage is called; the bold stretches are where each zone takes over. In stage 1 the upper blade carries the largest currents (the strongest colour; at rest its |CSD| is 2.5× "
           "the hilus's), but the hilus rises first and most: past 15× at 0.2 s against 0.5 s, and to 59× against 28× at 0.7 s. "
           "One opportunistic seizure."])
h48 = th(48, 1.5)
place(48, L3, y, R3 - L3, h48 + 0.02)
SEZ_END = y + h48 + PAD_BOTTOM
card((43, 44, 45), TOP, SEZ_END - TOP)
# ================================================================== column 3: optogenetics
TOPO = SEZ_END + G_CARD
card((49, 50, 51), TOPO, 1.0)
place(52, y=TOPO + (BAND - 0.46) / 2); place(53, y=TOPO + (BAND - 0.46) / 2)
y = TOPO + BAND + PAD_TOP
para_runs(54, 0, ["F  Light drives an SST unit, and its bursts lock to the light, most at 5 Hz"])
hF = subheading(54, L3, y, R3 - L3, 26)
y += hF + G_HEAD
wF, hF_ = picture(55, P("F_opto.png"), L3, y)
delete(83)
delete(56)
delete(58)
y += hF_ + G_CAP
size(57, 15)
texts(57, ["One light-driven SST interneuron (left: it carries ChR2), one column per condition: the light (one blue tick per "
           "pulse), 9 s of raw LFP, its spectrogram and the unit's spikes, then its spike autocorrelation, scaled to its peak "
           "(blue marks: one light period apart). Right (arrows): the unit's firing rate, from its spikes, and its rhythm strength, "
           "its autocorrelation's power at the light frequency; every run (two runs at 5 and 10 Hz). ", "Kcnt1", " Y777H mouse with ChR2 in SST cells, H3 probe; redrawn from the numbers in our 2024 poster. "
           "Light order: rest, 10, rest, 10, 5, 7, 12, 5 Hz."])
h57 = th(57, 0.75)
place(57, L3, y, R3 - L3, h57 + 0.02)
OPTO_END = y + h57 + PAD_BOTTOM
card((49, 50, 51), TOPO, OPTO_END - TOPO)
# ================================================================== column 3: conclusions (the rest of the column)
TOPC = OPTO_END + G_CARD
card((65, 66, 67), TOPC, BOTTOM - TOPC)
place(66, h=BAND_C); place(67, h=BAND_C)
para_runs(68, 2, ["3. Hilar inhibition gives way first. ", "A hilar interneuron fired at nearly 5× its baseline in the 3 s before "
                  "onset, then fell silent as the seizure spread."])
CSZ = float(os.environ.get("CONCL_PT", "21"))
size(68, CSZ)
h68 = th(68, 2.6)
avail = BOTTOM - (TOPC + BAND_C)
place(68, L3, TOPC + BAND_C + (avail - h68) / 2, R3 - L3, h68 + 0.02)     # centred in the card under its band
log += [("seizure card ends", SEZ_END), ("opto card ends", OPTO_END), ("conclusions: room / text", (avail, h68))]

t.write(sp, xml_declaration=True, encoding="UTF-8", standalone=True)
rels.write(rp, xml_declaration=True, encoding="UTF-8", standalone=True)
shutil.rmtree(TRIM)
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
    print("%-34s %s" % (n, ("(%.2f, %.2f)" % hv) if isinstance(hv, tuple) else "%.2f" % hv))
print("measured text from", sys.argv[4] if len(sys.argv) > 4 else "(none: estimates)", "| wrote", OUT)
