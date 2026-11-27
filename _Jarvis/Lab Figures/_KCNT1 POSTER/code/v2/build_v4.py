"""v4 = v3 with the Methods IED replaced ('IED sucks try again'): a bigger, full-depth IED with its high-frequency burst at
the center, and both events on shared voltage and CSD scales; spectrograms in Jarvis's stacked 8-contact style.
usage: python build_v4.py UNPACKED_V3 METHODS_PNG OUT.pptx"""
import os, shutil, sys, zipfile
from lxml import etree
from PIL import Image
SRC, PNG, OUT = sys.argv[1:4]
W = OUT + ".unpacked"
shutil.rmtree(W, ignore_errors=True); shutil.copytree(SRC, W)
NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main", "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships", "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
sp, rp = os.path.join(W, "ppt/slides/slide1.xml"), os.path.join(W, "ppt/slides/_rels/slide1.xml.rels")
t, rels = etree.parse(sp), etree.parse(rp)
el = lambda i: t.xpath("//p:cNvPr[@id='%d']/ancestor::*[self::p:sp or self::p:pic][1]" % i, namespaces=NS)[0]
pic = el(25)
rid = pic.find(".//a:blip", NS).get("{%s}embed" % NS["r"])
rel = rels.xpath("//pr:Relationship[@Id='%s']" % rid, namespaces=NS)[0]
old = os.path.join(W, "ppt", "media", os.path.basename(rel.get("Target")))
os.remove(old)
shutil.copy2(PNG, os.path.join(W, "ppt/media/image_methods_v4.png"))
rel.set("Target", "../media/image_methods_v4.png")
with Image.open(PNG) as im:
    ar = im.width / im.height
ext = pic.find(".//a:xfrm/a:ext", NS)
ext.set("cy", str(int(int(ext.get("cx")) / ar)))
runs = el(26).xpath(".//a:r", namespaces=NS)
texts = ["Reading the CSD (", "Kcnt1", " m1609, YH het). ",
         "A curated dentate spike (5–100 Hz) and a curated IED (>1 Hz) from one recording, drawn on the same voltage and CSD "
         "scales: voltage on the 32 even contacts, CSD (sinks blue, sources red) and spectrograms of eight contacts (dB over the "
         "recording's own baseline). The dentate spike puts brief sinks in both blades with a source between [5]; the IED is more "
         "than twice as large, runs from CA1 through both blades, and carries a burst of 100–600 Hz power at its center."]
assert len(runs) == 4, len(runs)
for r, s in zip(runs, texts):
    r.find("a:t", NS).text = s
t.write(sp, xml_declaration=True, encoding="UTF-8", standalone=True)
rels.write(rp, xml_declaration=True, encoding="UTF-8", standalone=True)
if os.path.exists(OUT): os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join(W, "[Content_Types].xml"), "[Content_Types].xml")
    for root, _d, fs in os.walk(W):
        for f in fs:
            a = os.path.relpath(os.path.join(root, f), W).replace(os.sep, "/")
            if a != "[Content_Types].xml": z.write(os.path.join(root, f), a)
shutil.rmtree(W)
print("wrote", OUT)
