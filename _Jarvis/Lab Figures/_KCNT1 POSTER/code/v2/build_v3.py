"""KCNT1 poster v3, built from v2 as the lab saved it (2026-11-25 21:39, with two new comments) by editing its XML.

  'There's way better IEDs out there... spans the entire recording depth and ~1st percentile spectrogram activity at
   the center' (Methods figure)  -> new spike: every unflagged spike in every committed Lock set was scored on VACC for
                                   depth span and 30-500 Hz power at its center; the figure now shows the best one.
  'Where discharges start and Acknowledgements have a lot of white space... work on the harmony of the poster and
   minimize wasted space' (Discharges card) -> all three columns end at the same line with 0.4 in gaps:
     column 2: Behavior, Where discharges start (re-laid out tighter, figures larger), then Acknowledgments | References
     column 3: Seizure onset back at full size (was 76%), SST optogenetics, Conclusions (card fitted to its text)
     Acknowledgments and References text larger, cards fitted to it.

usage: python build_v3.py UNPACKED_V2_DIR METHODS_PNG OUT.pptx
"""
import os
import re
import shutil
import sys
import zipfile

from lxml import etree
from PIL import Image

SRC, METHODS_PNG, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
WORK = OUT + ".unpacked"
EMU = 914400
NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
RNS = {"pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
R_EMBED = "{%s}embed" % NS["r"]

if os.path.exists(WORK):
    shutil.rmtree(WORK)
shutil.copytree(SRC, WORK)
slide_path = os.path.join(WORK, "ppt", "slides", "slide1.xml")
rels_path = os.path.join(WORK, "ppt", "slides", "_rels", "slide1.xml.rels")
tree = etree.parse(slide_path)
rels = etree.parse(rels_path)


def el(i):
    return tree.xpath("//p:cNvPr[@id='%d']/ancestor::*[self::p:sp or self::p:pic][1]" % i, namespaces=NS)[0]


def xfrm(e):
    x = e.find(".//a:xfrm", NS)
    return x.find("a:off", NS), x.find("a:ext", NS)


def geom(e):
    o, s = xfrm(e)
    return [int(o.get("x")) / EMU, int(o.get("y")) / EMU, int(s.get("cx")) / EMU, int(s.get("cy")) / EMU]


def place(i, x=None, y=None, w=None, h=None):
    o, s = xfrm(el(i))
    for node, k, v in ((o, "x", x), (o, "y", y), (s, "cx", w), (s, "cy", h)):
        if v is not None:
            node.set(k, str(int(round(v * EMU))))


def move(ids, dx, dy):
    for i in ids:
        x, y, _w, _h = geom(el(i))
        place(i, x + dx, y + dy)


def font(i, pt):
    for r in el(i).xpath(".//a:rPr|.//a:endParaRPr", namespaces=NS):
        r.set("sz", str(int(pt * 100)))


def aspect_of(i):
    _x, _y, w, h = geom(el(i))
    return w / h


GAP = 0.40
TOP, BOTTOM = 6.00, 35.50

# ---------------------------------------------------------------- column 3: seizure full size, opto, conclusions
SEZ_H = 14.40
CON_H = 4.00
OPT_H = BOTTOM - TOP - SEZ_H - CON_H - 2 * GAP
sy0 = geom(el(43))[1]
move(range(43, 49), 0, TOP - sy0)
place(43, h=SEZ_H)
fa = aspect_of(47)
fig_y = TOP + 2.30
place(47, x=32.10, y=fig_y, w=15.0, h=15.0 / fa)
cap_y = fig_y + 15.0 / fa + 0.12
place(48, y=cap_y, h=TOP + SEZ_H - 0.12 - cap_y)

opt_y = TOP + SEZ_H + GAP
oy0 = geom(el(49))[1]
move([49, 50, 51, 52, 53, 54, 83, 55, 56, 57, 58], 0, opt_y - oy0)
place(49, h=OPT_H)

con_y = opt_y + OPT_H + GAP
cy0 = geom(el(65))[1]
move(range(65, 69), 0, con_y - cy0)
place(65, h=CON_H)
place(68, h=CON_H - 1.05)
font(68, 19)

# ---------------------------------------------------------------- column 2: behavior, discharges (tighter), ack | refs
FOOT_H = 2.30
dis_y = TOP + geom(el(59))[3] + GAP
DIS_H = BOTTOM - FOOT_H - GAP - dis_y
dy0 = geom(el(31))[1]
move(range(31, 43), 0, dis_y - dy0)
place(31, h=DIS_H)
inner_l, inner_r = 15.90, 30.90
sub_y = dis_y + 1.25
place(34, x=inner_l, y=sub_y, w=15.0)
col_y = sub_y + 0.70
bottom = dis_y + DIS_H - 0.18
# left: B figure and its caption
cap_h = 1.62
lw = (bottom - cap_h - 0.10 - col_y) * aspect_of(35)
place(35, x=inner_l, y=col_y, w=lw, h=lw / aspect_of(35))
place(36, x=inner_l, y=col_y + lw / aspect_of(35) + 0.10, w=lw, h=cap_h)
# right: C figure + caption, then D plot with its caption beside it
rx = inner_l + lw + 0.40
rw = inner_r - rx
place(37, x=rx, y=col_y - 0.05, w=rw, h=0.95)
cy = col_y + 0.95
a38 = aspect_of(38)
place(38, x=rx, y=cy, w=rw, h=rw / a38)
c39y = cy + rw / a38 + 0.08
place(39, x=rx, y=c39y, w=rw, h=1.15)
d_sub = c39y + 1.15 + 0.22
place(40, x=rx, y=d_sub, w=rw, h=0.90)
dpy = d_sub + 0.95
dph = bottom - dpy
a41 = aspect_of(41)
place(41, x=rx, y=dpy, w=dph * a41, h=dph)
place(42, x=rx + dph * a41 + 0.25, y=dpy + 0.10, w=rw - dph * a41 - 0.25, h=dph - 0.10)

foot_y = BOTTOM - FOOT_H
half_w = (15.80 - GAP) / 2
for ids, x0 in ((range(69, 75), 15.50), (range(75, 79), 15.50 + half_w + GAP)):
    ids = list(ids)
    cx0, cy0, _w, _h = geom(el(ids[0]))
    move(ids, x0 - cx0, foot_y - cy0)
for card, band, head in ((69, 70, 71), (75, 76, 77)):
    place(card, w=half_w, h=FOOT_H)
    place(band, w=half_w)
    place(head, w=half_w - 0.80)
font(72, 15)
place(72, w=half_w - 0.70, h=1.05)
place(73, y=foot_y + 0.70 + 1.12)
place(74, y=foot_y + 0.70 + 1.12)
font(78, 15.5)
place(78, w=half_w - 0.70, h=1.40)

# ---------------------------------------------------------------- Methods figure: new spike
rid = el(25).find(".//a:blip", NS).get(R_EMBED)
rel = rels.xpath("//pr:Relationship[@Id='%s']" % rid, namespaces=RNS)[0]
shutil.copy2(METHODS_PNG, os.path.join(WORK, "ppt", "media", "image_methods_v3.png"))
rel.set("Target", "../media/image_methods_v3.png")
with Image.open(METHODS_PNG) as im:
    ma = im.width / im.height
mx, my, mw, _mh = geom(el(25))
place(25, w=mw, h=mw / ma)

move([27, 28, 29, 30], 0, 0.30)   # the caption is a line longer; this row had room below it
# spike_caption: say what makes this spike the example
for t in el(26).xpath(".//a:t", namespaces=NS):
    if t.text and "with sinks in the same places." in t.text:
        t.text = t.text.replace("with sinks in the same places.", "with sinks in the same places; of this recording's 688 curated spikes it has the most 30–500 Hz power at its peak.")

# ---------------------------------------------------------------- comments: answered in v3, kept in v2
for r in rels.xpath("//pr:Relationship", namespaces=RNS):
    if "comments" in r.get("Type", "").lower():
        p = os.path.normpath(os.path.join(os.path.dirname(slide_path), r.get("Target")))
        r.getparent().remove(r)
        if os.path.exists(p):
            os.remove(p)
for cr in tree.xpath("//*[local-name()='commentRel']"):
    ext = cr.getparent()
    lst = ext.getparent()
    lst.remove(ext)
    if len(lst) == 0:
        lst.getparent().remove(lst)
ct_path = os.path.join(WORK, "[Content_Types].xml")
ct = open(ct_path, encoding="utf-8").read()
ct = re.sub(r'<Override PartName="/ppt/comments/[^"]+"[^>]*/>', "", ct)
open(ct_path, "w", encoding="utf-8").write(ct)

tree.write(slide_path, xml_declaration=True, encoding="UTF-8", standalone=True)
rels.write(rels_path, xml_declaration=True, encoding="UTF-8", standalone=True)
used = set()
for root, _d, files in os.walk(os.path.join(WORK, "ppt")):
    for f in files:
        if f.endswith(".rels"):
            used.update(re.findall(r'Target="[^"]*media/([^"]+)"', open(os.path.join(root, f), encoding="utf-8").read()))
for f in os.listdir(os.path.join(WORK, "ppt", "media")):
    if f not in used:
        os.remove(os.path.join(WORK, "ppt", "media", f))
if os.path.exists(OUT):
    os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(ct_path, "[Content_Types].xml")
    for root, _d, files in os.walk(WORK):
        for f in files:
            full = os.path.join(root, f)
            arc = os.path.relpath(full, WORK).replace(os.sep, "/")
            if arc != "[Content_Types].xml":
                z.write(full, arc)
shutil.rmtree(WORK)
print("wrote", OUT, "| discharges card %.2f in, opto %.2f in, B figure %.2f wide" % (DIS_H, OPT_H, lw))
