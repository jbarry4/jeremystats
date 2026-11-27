import sys, zipfile
from lxml import etree
NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main", "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
z = zipfile.ZipFile(sys.argv[1])
t = etree.fromstring(z.read("ppt/slides/slide1.xml"))
rels = etree.fromstring(z.read("ppt/slides/_rels/slide1.xml.rels"))
rmap = {r.get("Id"): r.get("Target") for r in rels}
E = 914400
for el in t.xpath("//p:spTree/*[self::p:sp or self::p:pic or self::p:grpSp or self::p:cxnSp or self::p:graphicFrame]", namespaces=NS):
    c = el.find(".//p:cNvPr", NS)
    off = el.find(".//a:xfrm/a:off", NS); ext = el.find(".//a:xfrm/a:ext", NS)
    if off is None:
        off = el.find(".//p:xfrm/a:off", NS); ext = el.find(".//p:xfrm/a:ext", NS)
    x, y = int(off.get("x")) / E, int(off.get("y")) / E
    w, h = int(ext.get("cx")) / E, int(ext.get("cy")) / E
    tag = etree.QName(el).localname
    txt = "".join(el.xpath(".//a:t/text()", namespaces=NS))[:70]
    blip = el.find(".//a:blip", NS)
    img = rmap.get(blip.get("{%s}embed" % NS["r"]), "") if blip is not None else ""
    szs = sorted(set(r.get("sz") for r in el.xpath(".//a:rPr", namespaces=NS) if r.get("sz")))
    print(f"{c.get('id'):>3} {tag:4} x{x:6.2f} y{y:6.2f} w{w:6.2f} h{h:6.2f}  {c.get('name')[:22]:22} {img[-28:]:28} sz{szs} | {txt}")
