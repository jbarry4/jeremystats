"""KCNT1 poster v6 = v4's deck with v6's figures (the v5 style plus the user's v5 comments) and captions to match.
What changed from v5: the lab's cell colours everywhere (CA1 green, granule cells pink, hilus and SST cells amber), the lab's
cell icons in the methods figures, the seizure stages drawn on the real section the probe went down, F and G merged into one
grid, Hom f-I curves beside the Het ones, the dentate circuit with PV cells, framed histology and a drawn arena.
usage: python build_v6.py V4.pptx OUTDIR_OF_PNGS OUT.pptx"""
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
el = lambda i: t.xpath("//p:cNvPr[@id='%d']/ancestor::*[self::p:sp or self::p:pic][1]" % i, namespaces=NS)[0]   # noqa: E731


def place(i, x=None, y=None, w=None, h=None):
    x_ = el(i).find(".//a:xfrm", NS)
    o, s = x_.find("a:off", NS), x_.find("a:ext", NS)
    for node, k, v in ((o, "x", x), (o, "y", y), (s, "cx", w), (s, "cy", h)):
        if v is not None:
            node.set(k, str(int(round(v * EMU))))


def _drop_media(rid):
    rel = rels.xpath("//pr:Relationship[@Id='%s']" % rid, namespaces=NS)[0]
    users = [r for r in rels.xpath("//pr:Relationship", namespaces=NS) if r.get("Target") == rel.get("Target")]
    path = os.path.normpath(os.path.join(W, "ppt", "slides", rel.get("Target")))
    return rel, users, path


def picture(i, png, x, y, w):
    pic = el(i)
    blip = pic.find(".//a:blip", NS)
    rel, users, old = _drop_media(blip.get("{%s}embed" % NS["r"]))
    name = "image_v6_" + os.path.basename(png)
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
    """remove a shape; a picture's image goes too when nothing else uses it."""
    e = el(i)
    blip = e.find(".//a:blip", NS)
    if blip is not None:
        rel, users, path = _drop_media(blip.get("{%s}embed" % NS["r"]))
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


P = lambda n: os.path.join(PNG, n)   # noqa: E731
log = []
# ------------------------------------------------------------------ column 1: introduction
place(12, 0.9, 7.3, 13.8, 3.3)
para_runs(12, 1, ["Homozygous mice carrying a patient variant (", "Kcnt1", " Y777H, human Y796H) have frequent, sleep-related seizures and "
                  "interictal epileptiform discharges (IEDs) that map to motor cortex [3]. The extra K", "+", " current quiets inhibitory "
                  "neurons, not excitatory ones: SST-type interneurons fire less in heterozygous and homozygous mice, while PV-type "
                  "interneurons fire more in heterozygous and less in homozygous mice [3, 4]."])
YF = 10.7
h = picture(13, P("I_fI.png"), 0.9, YF, 7.4); log.append(("I_fI", h))
place(14, 0.9, YF + h + 0.05, 7.4, 1.12)
texts(14, ["SST", " and ", "PV", "-type interneurons under KCNT1 gain of function, each against its own WT (grey), mean ± SEM. Top: "
           "YH Het (orange; Shore et al., eLife 2024, Fig. 4C, CC BY 4.0). Bottom: YH Hom non-fast-spiking and fast-spiking "
           "cells (purple; Shore et al., Cell Rep 2020, Fig. 4). Redrawn; traces at one scale."])
hc = picture(15, P("I_circuit.png"), 8.75, YF + 0.05, 5.9); log.append(("I_circuit", hc))
place(16, 8.75, YF + 0.05 + hc + 0.08, 5.9, 1.65)
texts(16, ["Entorhinal input reaches the granule cells' (pink) dendrites: lateral (LEC) in the outer and medial (MEC) in the middle "
           "molecular layer. Hilar SST (HIPP) cells inhibit the outer dendrites, where LEC input lands; PV basket cells inhibit the "
           "granule cells' somata [6]."])
YH = YF + h + 0.05 + 1.12 + 0.18
place(17, 0.9, YH, 13.8, 1.2)
place(18, 1.2, YH + 0.04, 13.2, 1.12)
INTRO_END = YH + 1.2 + 0.18
place(9, h=INTRO_END - 6.0)
log.append(("intro card ends", INTRO_END))
# ------------------------------------------------------------------ column 1: methods
TOPM = INTRO_END + 0.28
for i in (19, 20, 21):
    place(i, y=TOPM)
place(19, h=35.5 - TOPM)
y = TOPM + 1.35
h1 = picture(22, P("M_headfixed.png"), 0.9, y, 5.0)
h2 = picture(23, P("M_laminar.png"), 6.1, y, 8.6)
log += [("M_headfixed", h1), ("M_laminar", h2)]
y += max(h1, h2) + 0.05
place(24, 0.9, y, 13.8, 0.95)
texts(24, ["Recording. ", "Awake, head-fixed ", "Kcnt1", " Y777H WT, Het and Hom mice on a treadmill. A 64-contact silicon probe spans "
           "CA1 and both dentate blades (right: a control recording); for optogenetics, an optical fiber sits beside it. Current source "
           "density (CSD) maps where current enters cells (sinks, blue) and leaves them (sources, red)."])
y += 0.98
h = picture(25, P("M_events.png"), 0.9, y, 13.8); log.append(("M_events", h))
y += h + 0.05
place(26, 0.9, y, 13.8, 0.85)
texts(26, ["Reading the CSD (", "Kcnt1", " m1609, YH Het). ", "A curated dentate spike (5–100 Hz) and IED (>1 Hz) from one recording, "
           "on one voltage and one CSD scale; spectrograms in dB over each contact's baseline. The dentate spike puts brief sinks in "
           "both blades with a source between [5]; the IED is more than twice as large, runs from CA1 through both blades and carries "
           "a burst of 100–600 Hz power."])
y += 0.95
hh = picture(27, P("M_histology.png"), 0.9, y, 2.85); log.append(("M_histology", hh))
place(28, 3.95, y + 0.3, 4.05, 2.6)
texts(28, ["Optogenetics. ", "SST-Cre × ", "Kcnt1", " Y777H mice received Cre-dependent ChR2 (AAV-PHP.eB CAG-DIO-ChR2); the fiber "
           "delivered 5–12 Hz light. Left: SST (green) and NeuN (red) in the dentate, 20x; arrows, two SST cells."])
ha = picture(29, P("M_arena.png"), 8.25, y, 2.85); log.append(("M_arena", ha))
place(30, 11.3, y + 0.3, 3.4, 2.6)
log.append(("methods bottom row ends", y + max(hh, ha)))
# ------------------------------------------------------------------ column 2: behavior (as in v5)
h = picture(63, P("A_behavior.png"), 15.9, 7.95, 15.0); log.append(("A_behavior", h))
place(64, 15.9, 7.95 + h + 0.12, 15.0, 0.8)
BEH_END = 7.95 + h + 0.12 + 0.8 + 0.15
place(59, h=BEH_END - 6.0)
# ------------------------------------------------------------------ column 2: where discharges start (as in v5)
TOPD, BOTD = BEH_END + 0.4, 32.8
for i in (31, 32, 33):
    place(i, y=TOPD)
place(31, h=BOTD - TOPD)
SPARE = (BOTD - TOPD) - 13.3
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
# ------------------------------------------------------------------ column 3: seizure
para_runs(46, 0, ["E  The seizure starts in the hilus, then recruits both blades and CA1, as a hilar interneuron falls silent"])
h = picture(47, P("E_seizure.png"), 32.1, 8.3, 15.0); log.append(("E_seizure", h))
place(48, 32.1, 8.3 + h + 0.06, 15.0, 1.05)
texts(48, ["Spontaneous seizure in awake Hom mouse 459 (one of the six old Hom in A). ", "Top: ", "each stage on the atlas section the "
           "probe went down (Allen CCF layers, AP −1.9 mm), and the CSD (sinks blue, sources red) with the LFP over it. ", "Middle: ",
           "the hilar interneuron (CSC 41, sorted again from the raw) fired at 58 spikes/s in the 3 s before onset (4.7× its 12.4 Hz "
           "baseline) and in bursts to 2.3 s, then stopped: no spikes 2.6–3.7 s, 0.4 spikes/s after the seizure. ", "Bottom: ",
           "each zone's |CSD| against its own quiet baseline. One opportunistic seizure; no claims about seizure rate."])
# ------------------------------------------------------------------ column 3: optogenetics (F and G are one figure now)
place(54, 32.1, 22.02, 15.0, 0.55)
para_runs(54, 0, ["F  Light drives an SST unit, and its bursts lock to the light, most at 5 Hz"])
h = picture(55, P("F_opto.png"), 32.1, 22.62, 15.0); log.append(("F_opto", h))
delete(83)
delete(56)
delete(58)
place(57, 32.1, 22.62 + h + 0.06, 15.0, 1.1)
texts(57, ["One light-driven SST interneuron, one column per condition: 9 s of raw LFP, its spectrogram and the unit's spikes, then the "
           "unit's spike autocorrelation, scaled to its peak (blue ticks: one light period apart). Right: firing rate and rhythm power "
           "at the light frequency, every run (two runs at 5 and 10 Hz). ", "Kcnt1", " Y777H mouse with ChR2 in SST cells, H3 probe; "
           "redrawn from the numbers in our 2024 poster. Light order: rest, 10, rest, 10, 5, 7, 12, 5 Hz."])
log.append(("opto caption ends", 22.62 + h + 0.06 + 1.1))
# ------------------------------------------------------------------ conclusions
para_runs(68, 2, ["3. Hilar inhibition gives way first. ", "A hilar interneuron fired at nearly 5× its baseline in the 3 s before "
                  "onset, then fell silent as the seizure spread."])

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
    print("%-24s %.2f" % (n, h))
print("wrote", OUT)
