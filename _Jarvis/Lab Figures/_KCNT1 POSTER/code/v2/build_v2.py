"""KCNT1 poster v2, built from the lab's edited draft 1 (KCNT1_poster_draft1.pptx as saved 2026-11-25 20:31, with
Shahriar's six comments) by editing its XML in place, so everything else in draft 1 stays exactly as it was.

What changes (comment -> change):
  'Move behavior as the main start after intro and methods'  Behavior card to the top of column 2, beside the Intro;
                                   Discharges below it; Seizure to the top of column 3; panels re-lettered in reading
                                   order (Behavior A, discharges B-D, seizure E, opto F-G); conclusions follow the order.
  'Remove.' / 'Replace with new Jarvis figures, remove theta' (Methods CSD primer)  replaced by a new figure: one curated
                                   dentate spike and one curated (Lock) spike from KCNT1 m1609 s1, voltage, CSD and
                                   spectrograms; no theta.
  'Remove' (7 Hz CSD)              removed.
  'Add baseline, 5HZ, 7Hz, 12Hz figures as opto effects'   Dylan 2024 Fig. 7 panels A, B, D, F as panel F.
  'Add figure 7 as opto entrainment'  the burst-rhythmicity figure with its two summary curves (Dylan 2024 Fig. 8,
                                   = NBH'25 Fig. 7 plus summaries) as panel G.
  The two pasted screenshots and the six comments are not carried into v2 (draft 1 keeps them).

usage: python build_v2.py UNPACKED_DRAFT1_DIR NEW_ASSETS_DIR OUT.pptx
"""
import copy
import os
import re
import shutil
import sys
import zipfile

from lxml import etree
from PIL import Image

SRC, ASSETS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
WORK = OUT + ".unpacked"
EMU = 914400
NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
A = "{%s}" % NS["a"]
R_EMBED = "{%s}embed" % NS["r"]

if os.path.exists(WORK):
    shutil.rmtree(WORK)
shutil.copytree(SRC, WORK)
slide_path = os.path.join(WORK, "ppt", "slides", "slide1.xml")
rels_path = os.path.join(WORK, "ppt", "slides", "_rels", "slide1.xml.rels")
tree = etree.parse(slide_path)
rels = etree.parse(rels_path)
RNS = {"pr": "http://schemas.openxmlformats.org/package/2006/relationships"}


def el(i):
    found = tree.xpath("//p:cNvPr[@id='%d']/ancestor::*[self::p:sp or self::p:pic][1]" % i, namespaces=NS)
    assert found, i
    return found[0]


def xfrm(e):
    x = e.find(".//a:xfrm", NS)
    return x.find("a:off", NS), x.find("a:ext", NS)


def geom(e):
    o, s = xfrm(e)
    return [int(o.get("x")) / EMU, int(o.get("y")) / EMU, int(s.get("cx")) / EMU, int(s.get("cy")) / EMU]


def place(e, x=None, y=None, w=None, h=None):
    o, s = xfrm(e)
    if x is not None:
        o.set("x", str(int(round(x * EMU))))
    if y is not None:
        o.set("y", str(int(round(y * EMU))))
    if w is not None:
        s.set("cx", str(int(round(w * EMU))))
    if h is not None:
        s.set("cy", str(int(round(h * EMU))))


def move(ids, dx, dy):
    for i in ids:
        x, y, _w, _h = geom(el(i))
        place(el(i), x + dx, y + dy)


def runs_of(e):
    return e.xpath(".//a:p/a:r", namespaces=NS)


def set_text(e, parts, size=None):
    """Replace the shape's paragraphs with one paragraph per list in `parts`; each list holds (text, bold, italic)
    runs styled like the shape's first run (font, color); keeps the first paragraph's pPr."""
    body = e.find(".//p:txBody", NS)
    paras = body.findall("a:p", NS)
    tmpl_p = paras[0]
    tmpl_r = tmpl_p.find("a:r", NS)
    tmpl_rpr = copy.deepcopy(tmpl_r.find("a:rPr", NS))
    ppr = tmpl_p.find("a:pPr", NS)
    end = tmpl_p.find("a:endParaRPr", NS)
    for p in paras:
        body.remove(p)
    for runs in parts:
        p = etree.SubElement(body, A + "p")
        if ppr is not None:
            p.append(copy.deepcopy(ppr))
        for text, bold, italic in runs:
            r = etree.SubElement(p, A + "r")
            rpr = copy.deepcopy(tmpl_rpr)
            for k in ("b", "i"):
                if k in rpr.attrib:
                    del rpr.attrib[k]
            if bold:
                rpr.set("b", "1")
            if italic:
                rpr.set("i", "1")
            if size:
                rpr.set("sz", str(int(size * 100)))
            r.append(rpr)
            t = etree.SubElement(r, A + "t")
            t.text = text
            if text != text.strip():
                t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        if end is not None:
            e2 = copy.deepcopy(end)
            if size:
                e2.set("sz", str(int(size * 100)))
            p.append(e2)


def relabel(i, old, new):
    r = runs_of(el(i))[0]
    t = r.find("a:t", NS)
    assert t.text.startswith(old), (i, t.text)
    t.text = new + t.text[len(old):]


def replace_in(i, old, new):
    hit = 0
    for r in runs_of(el(i)):
        t = r.find("a:t", NS)
        if t is not None and t.text and old in t.text:
            t.text = t.text.replace(old, new)
            hit += 1
    assert hit, (i, old)


def rid_of(i):
    return el(i).find(".//a:blip", NS).get(R_EMBED)


def retarget(i, media_name, name, descr):
    """Point picture i at a new media file; drop any crop; rename it for the Selection pane."""
    rid = rid_of(i)
    rel = rels.xpath("//pr:Relationship[@Id='%s']" % rid, namespaces=RNS)[0]
    rel.set("Target", "../media/" + media_name)
    pic = el(i)
    for sr in pic.findall(".//a:srcRect", NS):
        sr.getparent().remove(sr)
    nv = pic.find(".//p:cNvPr", NS)
    nv.set("name", name)
    nv.set("descr", descr)


def remove(i):
    e = el(i)
    blip = e.find(".//a:blip", NS)
    if blip is not None:
        rid = blip.get(R_EMBED)
        for rel in rels.xpath("//pr:Relationship[@Id='%s']" % rid, namespaces=RNS):
            rel.getparent().remove(rel)
    e.getparent().remove(e)


def aspect(png):
    with Image.open(os.path.join(ASSETS, png)) as im:
        return im.width / im.height


# ----------------------------------------------------------------- media
NEW = {"image20.png": "methods_ds_and_spike_m1609.png", "image21.png": "opto_effects.png", "image22.png": "opto_entrainment.png"}
for dst, src in NEW.items():
    shutil.copy2(os.path.join(ASSETS, src), os.path.join(WORK, "ppt", "media", dst))

# ----------------------------------------------------------------- column 2: Behavior on top, Discharges under it
BEH = range(59, 65)          # card, band, heading, subheading, figure, caption
DIS = range(31, 43)
SEZ = range(43, 49)
OPT = [49, 50, 51, 52, 53, 54, 55, 56, 57, 58]
bx, by, _bw, bh = geom(el(59))
move(BEH, 15.50 - bx, 6.00 - by)
move(DIS, 0.0, (6.00 + bh + 0.40) - geom(el(31))[1])

# ----------------------------------------------------------------- column 3: Seizure on top (smaller), Opto, then the rest
sx, sy, _sw, _sh = geom(el(43))
move(SEZ, 31.70 - sx, 6.00 - sy)
SEZ_H = 12.35
place(el(43), h=SEZ_H)
cap_h = geom(el(48))[3]
cap_y = 6.00 + SEZ_H - 0.15 - cap_h
fig_y = geom(el(47))[1]
fig_h = cap_y - 0.10 - fig_y
fig_w = fig_h * (geom(el(47))[2] / geom(el(47))[3])   # keep the figure's own aspect
place(el(47), x=32.10 + (15.0 - fig_w) / 2, w=fig_w, h=fig_h)
place(el(48), y=cap_y)

OPT_Y = 6.00 + SEZ_H + 0.40
OPT_H = 29.45 - 0.40 - OPT_Y          # down to the Conclusions card, which stays where it is
ox, oy, _ow, _oh = geom(el(49))
move(OPT, 0.0, OPT_Y - oy)
place(el(49), h=OPT_H)
remove(80)                            # the two pasted screenshots
remove(82)
# F (effects) and G (entrainment), side by side at one height
sub_y = OPT_Y + 1.25
fig_top = sub_y + 0.62
cap_hh = 1.05
fig_bot = OPT_Y + OPT_H - 0.15 - cap_hh - 0.08
hf = fig_bot - fig_top
we, wg = hf * aspect("opto_effects.png"), hf * aspect("opto_entrainment.png")
gap = 0.30
xe = 32.10
xg = xe + we + gap
assert xg + wg <= 47.10 + 1e-6, (we, wg)
retarget(55, "image21.png", "Opto effects (Dylan 2024 Fig. 7 A, B, D, F)",
         "LFP, spectrogram and one SST unit's spikes at baseline and during 5, 7 and 12 Hz light")
retarget(56, "image22.png", "Opto entrainment (Dylan 2024 Fig. 8)",
         "Burst rhythmicity of a light-driven SST interneuron: autocorrelation and spectrum per light frequency, "
         "mean burst power and mean firing rate")
place(el(55), x=xe, y=fig_top, w=we, h=hf)
place(el(56), x=xg, y=fig_top, w=wg, h=hf)
place(el(54), x=xe, y=sub_y, w=we, h=0.55)
set_text(el(54), [[("F  Opto effects: baseline, 5, 7 and 12 Hz light", True, False)]])
g = copy.deepcopy(el(54))
nv = g.find(".//p:cNvPr", NS)
nv.set("id", "83")
nv.set("name", "G subheading")
el(54).addnext(g)
place(el(83), x=xg, y=sub_y, w=wg, h=0.55)
set_text(el(83), [[("G  Opto entrainment", True, False)]])
cap_y2 = fig_bot + 0.08
place(el(57), x=xe, y=cap_y2, w=we, h=cap_hh)
set_text(el(57), [[("Raw LFP (top), spectrogram (middle) and spikes of one light-driven SST interneuron (bottom), 10 s at "
                    "baseline and during 5, 7 and 12 Hz light; ", False, False), ("Kcnt1", False, True),
                   (" Y777H mouse with ChR2 in SST cells, H3 probe. Light order in the session: rest, 10, rest, 10, 5, 7, "
                    "12, 5 Hz. One example (2024).", False, False)]])
place(el(58), x=xg, y=cap_y2, w=wg, h=cap_hh)
set_text(el(58), [[("The same unit: spike autocorrelation and spectrum per frequency, mean burst power and firing rate. "
                    "Strongest at 5 Hz, weakest at 12 Hz.", False, False)]], size=14)

# ----------------------------------------------------------------- Methods: the new Jarvis figure, no theta
mx, my, mw, _mh = geom(el(25))
retarget(25, "image20.png", "Dentate spike and spike, KCNT1 m1609 (new)",
         "A curated dentate spike and a curated spike from KCNT1 m1609 s1: voltage, CSD and spectrograms")
place(el(25), w=mw, h=mw / aspect("methods_ds_and_spike_m1609.png"))
place(el(26), y=my + mw / aspect("methods_ds_and_spike_m1609.png") + 0.05, h=1.15)
set_text(el(26), [[("Reading the CSD (", True, False), ("Kcnt1", True, True), (" m1609, YH het). ", True, False),
                   ("A curated dentate spike (5–100 Hz) and a curated spike (IED; unfiltered) from one recording, 300 ms "
                    "each: voltage on the 32 even contacts, CSD (sinks blue, sources red) and spectrograms at the four marked "
                    "contacts. The dentate spike puts brief sinks in both blades with a source between [5]; the IED (note the "
                    "2 mV scale) is larger and sharper, with sinks in the same places.", False, False)]], size=16)

# ----------------------------------------------------------------- letters in reading order, and the text that points at them
relabel(62, "F  ", "A  ")
relabel(34, "A  ", "B  ")
relabel(37, "B  ", "C  ")
relabel(40, "C  ", "D  ")
relabel(46, "D  ", "E  ")
replace_in(48, "old Hom in F)", "old Hom in A)")
replace_in(39, "one or the other (Methods).", "one or the other [5].")
set_text(el(68), [
    [("1. Learning suffers with age. ", True, False), ("Old Hom mice fail to improve overnight; young Hom and Het learn like WT.", False, False)],
    [("2. Discharges start in the hilus. ", True, False), ("The first sink of an IED and of a seizure lies in the hilus; the blades and CA1 follow.", False, False)],
    [("3. Hilar inhibition gives way first. ", True, False), ("A hilar interneuron fired at 3× baseline, then fell silent as the seizure began.", False, False)],
    [("4. SST interneurons follow light, best at 5 Hz. ", True, False), ("Driven at 5, 7 and 12 Hz, their bursts entrain most strongly at 5 Hz and least at 12 Hz.", False, False)],
    [("Next: ", True, False), ("SST and PV optogenetic rescue during discharges and learning, in larger cohorts with WT controls.", False, False)],
])

# ----------------------------------------------------------------- comments: resolved in v2, kept in draft 1
for rel in rels.xpath("//pr:Relationship", namespaces=RNS):
    if "comments" in rel.get("Type", "").lower():
        cpath = os.path.normpath(os.path.join(os.path.dirname(slide_path), rel.get("Target")))
        rel.getparent().remove(rel)
        if os.path.exists(cpath):
            os.remove(cpath)
for cr in tree.xpath("//*[local-name()='commentRel']"):       # the slide's pointer to its comment part
    ext = cr.getparent()
    lst = ext.getparent()
    lst.remove(ext)
    if len(lst) == 0:
        lst.getparent().remove(lst)
ct_path = os.path.join(WORK, "[Content_Types].xml")
ct = open(ct_path, encoding="utf-8").read()
ct = re.sub(r'<Override PartName="/ppt/comments/[^"]+"[^>]*/>', "", ct)
open(ct_path, "w", encoding="utf-8").write(ct)
cdir = os.path.join(WORK, "ppt", "comments")
if os.path.isdir(cdir) and not os.listdir(cdir):
    os.rmdir(cdir)

tree.write(slide_path, xml_declaration=True, encoding="UTF-8", standalone=True)
rels.write(rels_path, xml_declaration=True, encoding="UTF-8", standalone=True)

# media nobody points at any more (the old primer, 7 Hz CSD, old entrainment crop, the two screenshots)
used = set()
for root, _d, files in os.walk(os.path.join(WORK, "ppt")):
    for f in files:
        if f.endswith(".rels"):
            used.update(re.findall(r'Target="[^"]*media/([^"]+)"', open(os.path.join(root, f), encoding="utf-8").read()))
for f in os.listdir(os.path.join(WORK, "ppt", "media")):
    if f not in used:
        os.remove(os.path.join(WORK, "ppt", "media", f))
        print("dropped unused media", f)

# zip: [Content_Types].xml first
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
print("wrote", OUT)
print("seizure figure %.2f x %.2f in; opto figures %.2f + %.2f x %.2f in" % (fig_w, fig_h, we, wg, hf))
