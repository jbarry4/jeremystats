"""KCNT1 poster v5 = v4 with every figure rebuilt in one style (v5/style.py: Calibri, print-size type, one genotype palette,
one region palette, CSD sinks blue / sources red everywhere, jet spectrograms), laid out at its print size, and the captions
updated to match what the new figures show.
usage: python build_v5.py V4.pptx OUTDIR_OF_PNGS OUT.pptx"""
import os, shutil, sys, zipfile
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
sp, rp = os.path.join(W, "ppt/slides/slide1.xml"), os.path.join(W, "ppt/slides/_rels/slide1.xml.rels")
t, rels = etree.parse(sp), etree.parse(rp)
el = lambda i: t.xpath("//p:cNvPr[@id='%d']/ancestor::*[self::p:sp or self::p:pic][1]" % i, namespaces=NS)[0]


def place(i, x=None, y=None, w=None, h=None):
    x_ = el(i).find(".//a:xfrm", NS)
    o, s = x_.find("a:off", NS), x_.find("a:ext", NS)
    for node, k, v in ((o, "x", x), (o, "y", y), (s, "cx", w), (s, "cy", h)):
        if v is not None:
            node.set(k, str(int(round(v * EMU))))


def picture(i, png, x, y, w):
    pic = el(i)
    blip = pic.find(".//a:blip", NS)
    rid = blip.get("{%s}embed" % NS["r"])
    rel = rels.xpath("//pr:Relationship[@Id='%s']" % rid, namespaces=NS)[0]
    old = os.path.normpath(os.path.join(W, "ppt", "slides", rel.get("Target")))
    users = [r for r in rels.xpath("//pr:Relationship", namespaces=NS) if r.get("Target") == rel.get("Target")]
    name = "image_v5_" + os.path.basename(png)
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


P = lambda n: os.path.join(PNG, n)
log = []
# ------------------------------------------------------------------ column 1: introduction
h = picture(13, P("I_fI.png"), 0.9, 10.45, 7.4); log.append(("I_fI", h))
place(14, 0.9, 10.45 + h + 0.05, 7.4, 1.05)
h = picture(15, P("I_circuit.png"), 8.75, 10.5, 5.9); log.append(("I_circuit", h))
place(16, 8.75, 10.5 + h + 0.08, 5.9, 1.4)
texts(14, ["SST", " and ", "PV", " interneurons from YH Het mice (orange) vs WT (grey): the same current drives fewer spikes in SST "
           "cells and more in PV cells. Redrawn from Shore et al., eLife 2024, Fig. 4C (CC BY 4.0)."])
# ------------------------------------------------------------------ column 1: methods
h1 = picture(22, P("M_headfixed.png"), 0.9, 20.95, 5.0)
h2 = picture(23, P("M_laminar.png"), 6.1, 20.95, 8.6)
log += [("M_headfixed", h1), ("M_laminar", h2)]
place(24, 0.9, 20.95 + max(h1, h2) + 0.08, 13.8, 0.95)
texts(24, ["Recording. ", "Awake, head-fixed ", "Kcnt1", " Y777H WT, Het and Hom mice on a treadmill. A 64-contact silicon probe spans "
           "CA1 and both dentate blades (right: a control recording); for optogenetics, an optical fiber sits beside it. Current source "
           "density (CSD) maps where current enters cells (sinks, blue) and leaves them (sources, red)."])
h = picture(25, P("M_events.png"), 0.9, 25.72, 13.8); log.append(("M_events", h))
place(26, 0.9, 25.72 + h + 0.08, 13.8, 1.2)
h = picture(27, P("M_histology.png"), 0.9, 32.3, 2.6); log.append(("M_histology", h))
h = picture(29, P("M_arena.png"), 8.4, 32.3, 2.6); log.append(("M_arena", h))
# ------------------------------------------------------------------ column 2: behavior
h = picture(63, P("A_behavior.png"), 15.9, 7.95, 15.0); log.append(("A_behavior", h))
place(64, 15.9, 7.95 + h + 0.12, 15.0, 0.8)
BEH_END = 7.95 + h + 0.12 + 0.8 + 0.15                  # the card ends just under its caption
place(59, h=BEH_END - 6.0)
# ------------------------------------------------------------------ column 2: where discharges start (moved up into the space)
TOPD, BOTD = BEH_END + 0.4, 32.8
for i in (31, 32, 33):
    place(i, y=TOPD)
place(31, h=BOTD - TOPD)
SPARE = (BOTD - TOPD) - 13.3                            # what the card gained, shared between its sections
place(34, 15.9, TOPD + 1.25, 15.0, 0.6)
h = picture(35, P("B_ied.png"), 15.9, TOPD + 1.88 + SPARE * 0.25, 15.0); log.append(("B_ied", h))
yb = TOPD + 1.88 + SPARE * 0.25 + h
place(36, 15.9, yb + 0.05, 15.0, 0.72)
texts(36, ["One IED in a KCNT1 mouse (our 2025 poster, redrawn). ", "Left: ", "CSD (sinks blue, sources red) with the LFP of cortex, CA1 "
           "and hilus over it, and the probe track; the first sink is in the hilus, then CA1 and cortex follow. ", "Right: ",
           "before the IED, hilar LFP carries β–γ power that CA1 lacks, and hilar units (300–6000 Hz) fire."])
yc = yb + 0.05 + 0.72 + 0.1 + SPARE * 0.4
place(37, 15.9, yc, 10.0, 0.95)
place(40, 26.25, yc, 4.65, 0.95)
h = picture(38, P("C_ds.png"), 15.9, yc + 0.98 + SPARE * 0.15, 10.0); log.append(("C_ds", h))
place(39, 15.9, yc + 0.98 + SPARE * 0.15 + h + 0.05, 10.0, 0.9)
texts(39, ["Left: ", "a discharge in two steps: a sink at the OML and hilus (1), then 3 ms later sinks at OML and MML together (2) and "
           "a ~600 ms deflection. ", "Right: ", "a KCNT1 dentate spike, larger than in controls, again with OML and MML sinks at once "
           "(its profile in black over phase 2 in grey); a control DS uses one or the other [5]. One CSD scale for both."])
hd = picture(41, P("D_urethane.png"), 26.25, yc + 0.98 + SPARE * 0.15, 4.6); log.append(("D_urethane", hd))
place(42, 26.25, yc + 0.98 + SPARE * 0.15 + hd + 0.05, 4.65, 1.75)
log.append(("behavior card ends", BEH_END)); log.append(("discharges card", TOPD)); log.append(("spare", SPARE))
# ------------------------------------------------------------------ column 3: seizure
h = picture(47, P("E_seizure.png"), 32.1, 8.3, 15.0); log.append(("E_seizure", h))
place(48, 32.1, 8.3 + h + 0.06, 15.0, 1.05)
texts(48, ["Spontaneous seizure in awake Hom mouse 459 (one of the six old Hom in A). ", "Top: ", "where the discharge is at each stage, "
           "and the CSD (sinks blue, sources red) with the LFP over it. ", "Middle: ", "the hilar interneuron (CSC 41, sorted again from "
           "the raw) fired at 58 spikes/s over the last 3 s before onset, 4.7× its 12.4 Hz baseline, then fell nearly silent (0.4 "
           "spikes/s from 3 to 80 s). ", "Bottom: ", "each zone's |CSD| against its own quiet baseline. One opportunistic seizure; no "
           "claims about seizure rate."])
# ------------------------------------------------------------------ column 3: optogenetics
place(54, 32.1, 22.02, 8.2, 0.55)
h = picture(55, P("F_opto.png"), 32.1, 22.62, 15.0); log.append(("F_opto", h))
yg = 22.62 + h + 0.04
place(83, 32.1, yg, 15.0, 0.5)
para_runs(83, 0, ["G  The unit's bursts lock to the light, most at 5 Hz"]) if len(el(83).xpath(".//a:r", namespaces=NS)) == 1 else None
h = picture(56, P("G_entrain.png"), 32.1, yg + 0.52, 15.0); log.append(("G_entrain", h))
place(57, 32.1, yg + 0.52 + h + 0.04, 15.0, 1.1)
texts(57, ["Raw LFP, spectrogram and spikes of one light-driven SST interneuron, 9 s at baseline and during 5, 7 and 12 Hz light (F), "
           "and its spike autocorrelation, each scaled to its peak (G); right: firing rate and rhythm power at the light frequency for "
           "every run (two runs at 5 and 10 Hz). ", "Kcnt1", " Y777H mouse with ChR2 in SST cells, H3 probe; redrawn from the numbers "
           "in our 2024 poster. Light order: rest, 10, rest, 10, 5, 7, 12, 5 Hz."])
g58 = el(58)
g58.getparent().remove(g58)
# ------------------------------------------------------------------ conclusions
para_runs(68, 2, ["3. Hilar inhibition gives way first. ", "A hilar interneuron fired at nearly 5× its baseline in the 3 s before "
                  "onset, then fell silent as the seizure began."])

t.write(sp, xml_declaration=True, encoding="UTF-8", standalone=True)
rels.write(rp, xml_declaration=True, encoding="UTF-8", standalone=True)
if os.path.exists(OUT):
    os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join(W, "[Content_Types].xml"), "[Content_Types].xml")
    for root, _d, fs in os.walk(W):
        for f in fs:
            a = os.path.relpath(os.path.join(root, f), W).replace(os.sep, "/")
            if a != "[Content_Types].xml":
                z.write(os.path.join(root, f), a)
shutil.rmtree(W)
for n, h in log:
    print("%-12s %.2f in tall" % (n, h))
print("wrote", OUT)
