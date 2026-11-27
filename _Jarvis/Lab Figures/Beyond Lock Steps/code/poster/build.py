"""Build the 48 x 36 in PTEN poster in the UVM theme (python build.py, after assets.py and the menu's poster_ds.py and
poster_strip.py). Jan-26 figures come back for theta (A), IED initiation (B, C) and CNO (D); the DS story (E) is a new
draft figure; Behavior (F) and the writing sections are placeholders."""
import os

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
OUT = os.path.join(HERE, "PTEN_poster_template.pptx")

GREEN = RGBColor(0x15, 0x47, 0x34)      # UVM green
GOLD = RGBColor(0xFF, 0xD4, 0x16)       # UVM gold
PAGE = RGBColor(0xEE, 0xF1, 0xEE)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x1E, 0x1E, 0x1E)
MUTED = RGBColor(0x5A, 0x63, 0x5E)
PH_FILL = RGBColor(0xFF, 0xF8, 0xD6)
PH_LINE = RGBColor(0xC9, 0x9A, 0x00)
FONT = "Calibri"

# the pathway half of the old methods figure (the Pten;Raptor schematic and traces are cut off)
src = Image.open(os.path.join(IMG, "Picture_21.png"))
src.crop((0, 0, 1000, src.height)).save(os.path.join(IMG, "pathway_only.png"))
# the lab logo was drawn on black; make the black see-through so it sits on the green header
lab = Image.open(os.path.join(IMG, "Picture_50.png")).convert("RGBA")
lab.putdata([(r, g, b, 0 if max(r, g, b) < 40 else (a if max(r, g, b) > 90 else int(a * (max(r, g, b) - 40) / 50)))
             for r, g, b, a in lab.getdata()])
lab.save(os.path.join(IMG, "lab_logo_clear.png"))
tree = Image.open(os.path.join(IMG, "Picture_53.png"))
tree.crop((0, 0, int(round(tree.width * (1 - 0.7945))), tree.height)).save(os.path.join(IMG, "hope_tree.png"))

pres = Presentation()
pres.slide_width, pres.slide_height = Inches(48), Inches(36)
s = pres.slides.add_slide(pres.slide_layouts[6])
s.background.fill.solid()
s.background.fill.fore_color.rgb = PAGE


def aspect(name):
    w, h = Image.open(os.path.join(IMG, name)).size
    return w / h


def pic(name, x, y, w=None, h=None, nm=None):
    a = aspect(name)
    if w is None:
        w = h * a
    if h is None:
        h = w / a
    p = s.shapes.add_picture(os.path.join(IMG, name), Inches(x), Inches(y), width=Inches(w), height=Inches(h))
    if nm:
        p.name = nm
    return w, h


def box(x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE, name=None, dash=False, lw=0):
    sh = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(lw)
        if dash:
            sh.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    sh.shadow.inherit = False
    if name:
        sh.name = name
    return sh


def text(x, y, w, h, runs, size, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, name=None, italic=False):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, m, 0)
    paras = runs if isinstance(runs, list) else [runs]
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        segs = p if isinstance(p, tuple) else ((p, {}),)
        for seg, opt in segs:
            r = para.add_run()
            r.text = seg
            f = r.font
            f.name = FONT
            f.size = Pt(opt.get("size", size))
            f.bold = opt.get("bold", bold)
            f.italic = opt.get("italic", italic)
            f.color.rgb = opt.get("color", color)
            if opt.get("sup"):
                r._r.get_or_add_rPr().set("baseline", "30000")
    if name:
        tb.name = name
    return tb


def rich(x, y, w, h, paras, size=20, color=INK, space=8, name=None, anchor=MSO_ANCHOR.TOP):
    """Left-aligned paragraphs; each paragraph is a list of (text, opts) runs. "b" bolds a run, "c" colors it."""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, m, 0)
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.space_after = Pt(space)
        for seg, opt in p:
            r = para.add_run()
            r.text = seg
            f = r.font
            f.name = FONT
            f.size = Pt(opt.get("size", size))
            f.bold = opt.get("b", False)
            f.italic = opt.get("i", False)
            f.color.rgb = opt.get("c", color)
    if name:
        tb.name = name
    return tb


HDR = 1.1


def section(x, y, w, h, title, name):
    """A white card with a UVM-green heading band across its top."""
    box(x, y, w, h, WHITE, name=name + " card")
    box(x, y, w, HDR, GREEN, name=name + " heading band")
    text(x + 0.4, y, w - 0.8, HDR, title, 38, WHITE, True, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE, name=name + " heading")
    return y + HDR


def subhead(x, y, w, letter, s_, name, placeholder=False):
    rich(x, y, w, 0.5, [[(letter + "  ", {"b": True, "c": PH_LINE, "size": 26}),
                         (s_, {"b": True, "c": PH_LINE if placeholder else GREEN, "size": 24})]],
         name=name + " subheading")
    return y + 0.52


def chip(x, y, s_, name, right=None):
    """A small UVM-gold note; right= aligns its right edge there."""
    w = 0.115 * len(s_) + 0.45
    if right is not None:
        x = right - w
    box(x, y, w, 0.42, GOLD, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=name + " note")
    text(x, y, w, 0.42, s_, 16, GREEN, True, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE, name=name + " note text")


def draft(x, y, w, h, label, paras, name, size=20, space=8):
    """Placeholder TEXT: a dashed gold box with a tag and draft wording to rewrite."""
    box(x, y, w, h, PH_FILL, PH_LINE, name=name + " draft box", dash=True, lw=4)
    rich(x + 0.35, y + 0.25, w - 0.7, h - 0.4,
         [[("PLACEHOLDER TEXT  ", {"size": 17, "b": True, "c": PH_LINE}), (label, {"size": 17, "b": True, "c": GREEN})]] + paras,
         size, space=space, name=name + " draft text")


def figure_slot(x, y, w, h, label, note, name, size=30):
    box(x, y, w, h, WHITE, PH_LINE, name=name + " figure box", dash=True, lw=4)
    text(x + 0.5, y + 0.3, w - 1.0, h - 0.6,
         [(("PLACEHOLDER FIGURE", {"size": 18, "bold": True, "color": PH_LINE}),),
          ((label, {"size": size, "bold": True, "color": GREEN}),),
          ((note, {"size": 20, "color": MUTED}),)],
         20, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name=name + " figure label")


def b(t):
    return (t, {"b": True, "c": GREEN})


def n(t):
    return (t, {})


def ph(t):
    return (t, {"b": True, "c": PH_LINE})


# ---------- header ----------
box(0, 0, 48, 5.55, GREEN, name="Header band")
s.shapes.add_picture(os.path.join(IMG, "lab_logo_clear.png"), Inches(0.5), Inches(0.25), height=Inches(2.35))
s.shapes.add_picture(os.path.join(IMG, "Picture_490.png"), Inches(0.5), Inches(2.75), height=Inches(2.55))
s.shapes.add_picture(os.path.join(IMG, "Picture_6.png"), Inches(39.6), Inches(1.75), width=Inches(7.9))
text(7.4, 0.3, 31.8, 2.2, ["Dentate Spikes Carry a Signature of Interictal Discharges", "in Mosaic PTEN Knockout Mice"], 64, WHITE, True,
     PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE, name="Title")
authors = [("Hassaan Malik", "1*"), ("Rain Younger", "1,2*"), ("Shahriar Tafti", "1,2"), ("Isabella Piatek", "1"),
           ("Angelina Woychosky", "1"), ("Maddie Massad", "1"), ("Avery Sullenberger", "1"), ("Mackenzi L Prina", "3"),
           ("Bryan W Luikart", "3"), ("Jeremy Barry", "1")]
segs = []
for i, (nm, sup) in enumerate(authors):
    segs.append((nm, {}))
    segs.append((sup, {"sup": True}))
    if i < len(authors) - 1:
        segs.append((", ", {}))
text(7.4, 2.6, 31.8, 0.75, [tuple(segs)], 30, WHITE, align=PP_ALIGN.CENTER, name="Authors")
aff = ["Department of Neurological Sciences, Larner College of Medicine, University of Vermont, Burlington, VT",
       "Neuroscience Graduate Program, University of Vermont, Burlington, VT",
       "Department of Neurobiology, Heersink School of Medicine, University of Alabama at Birmingham, Birmingham, AL"]
text(7.4, 3.4, 31.8, 2.0, [((str(i + 1), {"sup": True, "color": GOLD}), (a, {"color": GOLD})) for i, a in enumerate(aff)]
     + [(("*", {"sup": True, "color": GOLD}), ("These authors contributed equally", {"color": GOLD, "italic": True}))], 24,
     align=PP_ALIGN.CENTER, name="Affiliations")

M, G = 0.5, 0.45
TOP = 5.55 + G
BOT = 36 - M
C1W = 14.6
X2 = M + C1W + G
CW = (48 - M - X2 - G) / 2          # result columns
X3 = X2 + CW + G
P = 0.35                            # inner padding

# ================= left column =================
IH = 4.85
cy = section(M, TOP, C1W, IH, "INTRODUCTION", "Introduction")
draft(M + P, cy + 0.25, C1W - 2 * P, IH - HDR - 0.5, "Introduction", [
    [n("Interictal epileptiform discharges (IEDs) mark a pathological hippocampus, while dentate spikes (DS) are normal "
       "population events in the dentate gyrus driven by entorhinal input. Mosaic PTEN loss in dentate granule neurons "
       "brings burst firing, theta hypersynchrony and slower spatial learning, and IEDs in some mice but not in others.")],
    [n("Here we ask whether IEDs grow out of the dentate spike: does the DS change with the share of knocked-out cells, and "
       "do events between a normal DS and an IED mark the mice that have IEDs?")]], "Introduction", size=19)

my = TOP + IH + G
IW = C1W - 2 * P
pw = 5.3
ph_ = pw / aspect("pathway_only.png")
m2h = 3.95
p7w, trw = m2h * aspect("p7_timeline.png"), m2h * aspect("traces_wt_ko.png")
hw = 10.2
hh = hw / aspect("Picture_42.png")
mh = HDR + 0.25 + ph_ + 0.3 + m2h + 0.05 + 0.36 + 0.2 + hh + 0.25
cy = section(M, my, C1W, mh, "METHODS", "Methods")
pic("pathway_only.png", M + P, cy + 0.25, w=pw, nm="PTEN pathway")
tx = M + P + pw + 0.35
rich(tx, cy + 0.2, M + C1W - P - tx, ph_ + 0.1, [
    [b("PTEN loss "), n("raises PI3K/AKT/mTOR signaling, driving neuronal overgrowth and burst firing.")],
    [b("Mosaic knockout: "), n("at P7, Pten flx/flx mice received a Cre retrovirus in the dentate gyrus (controls: GFP only); "
                               "the share of infected granule neurons (% KO) was counted in histology.")],
    [b("Groups: "), n("7 controls and 9 PTEN mice, 5 with IEDs (IED+) and 4 without (IED−).")],
    [b("Behavior: "), n("spatial accuracy task, before recording.")],
    [b("Recording: "), n("awake, head-fixed 5–6-month-old mice; a 64-contact silicon probe (20 µm spacing) from CA1 "
                         "through both dentate blades.")],
    [b("CNO: "), ph("[construct, dose and timing]")]], 19, space=7, name="Methods text")
ry = cy + 0.25 + ph_ + 0.3
x0 = M + (C1W - (p7w + 0.3 + trw)) / 2
pic("p7_timeline.png", x0, ry, h=m2h, nm="P7 timeline")
pic("traces_wt_ko.png", x0 + p7w + 0.3, ry, h=m2h, nm="Wildtype and Pten KO traces")
rich(M + P, ry + m2h + 0.05, IW, 0.36, [[("Cre retrovirus at P7; Pten KO granule neurons fire in bursts (arrowheads).",
                                         {"i": True, "c": MUTED})]], 16, name="Traces caption")
hy = ry + m2h + 0.05 + 0.36 + 0.2
pic("Picture_42.png", M + (C1W - hw) / 2, hy, w=hw, nm="Mouse and hippocampus")

by = my + mh + G
bh = BOT - by
cy = section(M, by, C1W, bh, "ISOLATING BIOMARKERS", "Isolating biomarkers")
pic("icon_vacc.png", M + P, cy + 0.22, h=0.55, nm="VACC icon")
rich(M + P + 0.8, cy + 0.2, IW - 0.8, 0.7, [[n("Terabytes of recordings, cataloged on the Vermont Advanced Computing Core (VACC), "
                                             "went through one custom pipeline:")]], 19, name="Biomarkers intro")
steps = [("detect", "Detect", "Two automated detectors flag candidates; their hits are pooled."),
         ("curate", "Curate", "Trained reviewers keep real events and reject artifacts."),
         ("align", "Align", "Each event's CSD is placed on the layers by its own sinks."),
         ("classify", "Classify", "Amplitude, half-width and fast power sort DS, BTs and IEDs.")]
colw = (IW - 3 * 0.22) / 4
sy = cy + 0.2 + 0.72 + 0.12
stw = colw
sth = stw / aspect("strip_1.png")
for k, (ic, head, body) in enumerate(steps):
    xx = M + P + k * (colw + 0.22)
    iw_, _ = pic("icon_%s.png" % ic, xx, sy, h=0.62, nm=head + " icon")
    text(xx + iw_ + 0.15, sy, colw - iw_ - 0.15, 0.62, [((str(k + 1) + "  ", {"color": PH_LINE}), (head, {}))], 24, GREEN, True,
         anchor=MSO_ANCHOR.MIDDLE, name=head + " name")
    pic("strip_%d.png" % (k + 1), xx, sy + 0.72, w=stw, nm=head + " data")
    box(xx, sy + 0.72, stw, sth, None, RGBColor(0xD6, 0xDB, 0xD8), name=head + " data frame", lw=1)
    rich(xx, sy + 0.72 + sth + 0.1, colw, 1.0, [[n(body)]], 17, name=head + " text")
rich(M + P, by + bh - 0.5, IW, 0.35, [[("Data strip: one IED+ mouse (m13) for 1–3; every event of all 16 mice for 4. "
                                       "Thanks to Bennet Fauber for VACC support.", {"i": True, "c": MUTED})]], 15, name="Acknowledgment")

# ================= middle column: theta and IED initiation =================
FW = CW - 2 * P
tw_ = CW - 2 * P - 0.6
th_ = tw_ / aspect("theta_A.png")
th_sec = HDR + 0.2 + 0.52 + 0.1 + th_ + 0.12 + 1.75 + 0.2
cy = section(X2, TOP, CW, th_sec, "THETA CSD", "Theta")
yy = subhead(X2 + P, cy + 0.2, FW, "A", "Theta currents are stronger in PTEN mice, most in the lower blade", "A")
pic("theta_A.png", X2 + (CW - tw_) / 2, yy + 0.1, w=tw_, nm="Theta rasters A")
chip(0, TOP + th_sec - 0.6, "Jan-26 figure · to update: remove the PTEN/RAPTOR line from Aiii", "A", right=X2 + CW - P)
yy += 0.1 + th_ + 0.12
rich(X2 + P, yy, FW, 1.75, [
    [b("Ai) Control: "), n("CSD maps current sinks (blue, into neurons) and sources (red); controls show steady 4–12 Hz theta.")],
    [b("Aii) PTEN: "), n("the largest theta currents, concentrated at the lower blade's granule and middle molecular layers.")],
    [b("Aiii) By layer: "), n("PTEN theta sinks are more than twice the controls' at GCL2 and MML2.")]], 19, space=5, name="A text")

y2 = TOP + th_sec + G
bw = FW - 1.2
bh_ = bw / aspect("Picture_7.png")
ch_ = bw / aspect("Picture_34.png")
ied_sec = BOT - 4.25 - G - y2
cy = section(X2, y2, CW, ied_sec, "IED INITIATION", "IED initiation")
yy = subhead(X2 + P, cy + 0.2, FW, "B", "IEDs start with a brief, layer-specific sink, then spread", "B")
pic("Picture_7.png", X2 + (CW - bw) / 2, yy + 0.08, w=bw, nm="IED initiation B")
yy += 0.08 + bh_ + 0.1
rich(X2 + P, yy, FW, 1.2, [
    [b("Bi) "), n("Scalograms show a vertical pillar of high-frequency power at IED onset.")],
    [b("Bii–Biii) "), n("The initiation phase (−1 to 0 ms) has its own sink pattern, unlike the propagation phase (2–15 ms).")],
    [b("Biv) "), n("The initiation sink overlaps the mean theta sinks.")]], 18, space=3, name="B text")
yy += 1.2
yy = subhead(X2 + P, yy, FW, "C", "IEDs arise from one consistent site at the lower granule layer", "C")
pic("Picture_34.png", X2 + (CW - bw) / 2, yy + 0.08, w=bw, nm="IED site C")
yy += 0.08 + ch_ + 0.1
rich(X2 + P, yy, FW, 1.25, [
    [b("Ci) "), n("172 IEDs over 10 sessions share one voltage pattern: a sharp onset with lasting hilar positivity and GCL2 negativity.")],
    [b("Cii) "), n("The CSD repeats it: a deep source with alternating sinks.  "), b("Ciii) "),
     n("The affected zone lines up with GCL2 in histology.")]], 18, space=3, name="C text")
chip(0, y2 + ied_sec - 0.6, "Jan-26 figures · to update with the current data", "BC", right=X2 + CW - P)

# ================= right column: the big picture, behavior =================
dw_ = FW - 0.6
dh_img = dw_ / aspect("Picture_29.png")
ew = FW
eh = ew / aspect("ds_story.png")
bp_sec = HDR + 0.2 + 0.52 + 0.08 + dh_img + 0.1 + 1.55 + 0.15 + 0.52 + 0.1 + eh + 0.1 + 1.25 + 0.2
cy = section(X3, TOP, CW, bp_sec, "THE BIG PICTURE: IEDs AND DENTATE SPIKES", "Big picture")
yy = subhead(X3 + P, cy + 0.2, FW, "D", "CNO lowers theta but leaves the IED trigger in place", "D")
pic("Picture_29.png", X3 + (CW - dw_) / 2, yy + 0.08, w=dw_, nm="CNO D")
yy += 0.08 + dh_img + 0.1
rich(X3 + P, yy, FW, 1.55, [
    [b("Di–Dii) "), n("Before and after CNO, initiation differs from propagation at HIL, MML2 and OML2 (all P < 0.002).")],
    [b("Diii–Div) "), n("CNO lowered theta CSD but not IED propagation; IEDs per 30 min: 8.2 ± 1.8 at baseline, "
                              "26.2 ± 8.3 after CNO.")],
    [b("Dv) "), n("GCL2 theta predicted the IED mice at baseline (AUC 0.82), much less after CNO (AUC 0.61).")]], 18, space=3,
     name="D text")
chip(0, cy + 0.24, "Jan-26 figure · update?", "D", right=X3 + CW - P)
yy += 1.55 + 0.15
yy = subhead(X3 + P, yy, FW, "E", "DS fast power marks the IED+ mice, and BTs bridge DS and IEDs", "E")
pic("ds_story.png", X3 + P, yy + 0.1, w=ew, nm="DS story E")
box(X3 + P - 0.08, yy + 0.02, ew + 0.16, eh + 0.16, None, PH_LINE, name="E placeholder frame", dash=True, lw=4)
chip(X3 + P + 0.15, yy + 0.12, "PLACEHOLDER FIGURE · draft from the DS analysis", "E")
yy += 0.1 + eh + 0.1
rich(X3 + P, yy, FW, 1.25, [
    [n("Every IED+ mouse's DS carry more fast power than every control's; every IED− mouse's carry less (m7, 24% KO "
       "without IEDs, lowest). Only the five IED+ mice make BTs and IED-class events above the control rate; within them "
       "fast power climbs from DS to BT to IED, and BTs carry more lower-MML current than the same mouse's DS.")]],
     18, name="E text")

y3 = TOP + bp_sec + G
beh_sec = BOT - 4.25 - G - y3
cy = section(X3, y3, CW, beh_sec, "BEHAVIOR", "Behavior")
yy = subhead(X3 + P, cy + 0.2, FW, "F", "[Finding: what the spatial accuracy task shows]", "F", placeholder=True)
dft_h = 2.35
slot_h = beh_sec - HDR - 0.2 - 0.52 - 0.1 - dft_h - 0.15 - 0.25
figure_slot(X3 + P, yy + 0.1, FW, slot_h, "Spatial accuracy task",
            "Trials to criterion and hidden-goal occupancy, WT against Pten KO", "Behavior")
draft(X3 + P, yy + 0.1 + slot_h + 0.15, FW, dft_h, "From the preprint (Abdulkareem et al., 2026), to update", [
    [n("Pten KO mice (n = 13) needed more training trials than WT mice (n = 19) to reach criterion (P < 0.001), and more "
       "knockout neurons in both hippocampi predicted more trials (ROC AUC > 0.8). In hidden-goal probes Pten KO mice spent "
       "less and less time at each new goal location (H2–H4, all P < 0.001 against WT).")]], "Behavior", size=18)

# ================= bottom row: discussion, funding, references =================
yb = BOT - 4.25
hb = 4.25
dw = 17.0
fw = 7.6
rw = 48 - M - X2 - dw - fw - 2 * G
cy = section(X2, yb, dw, hb, "DISCUSSION & CONCLUSION", "Discussion")
draft(X2 + P, cy + 0.22, dw - 2 * P, hb - HDR - 0.45, "Discussion & conclusion", [
    [b("1. A scalable pipeline. "), n("[Automated detection with expert review makes every event in every recording usable.]")],
    [b("2. One continuum. "), n("[DS, BTs and IEDs lie along one continuum; DS fast power marks the IED+ mice; m7 is the exception.]")],
    [b("3. Network state and trigger. "), n("[CNO lowers theta but not the IED trigger; treating network gain alone may miss it.]")]],
    "Discussion", size=18)

fx = X2 + dw + G
cy = section(fx, yb, fw, hb, "FUNDING", "Funding")
box(fx, cy, fw, hb - HDR, RGBColor(0x0B, 0x2A, 0x1F), name="Funding dark body")
lx = fx + P
pw_, _h = pic("Picture_9.png", lx, cy + 0.25, w=3.6, nm="PTEN Research logo")
nih_h = 1.15
pic("Picture_28.png", fx + fw - P - nih_h * aspect("Picture_28.png"), cy + 0.25, h=nih_h, nm="NIH logo")
ty = cy + 0.25 + 1.29 + 0.3
th = 0.95
tw = th * aspect("hope_tree.png")
pic("hope_tree.png", lx, ty, h=th, nm="HOPE tree")
text(lx + tw + 0.2, ty, 3.4, th, [(("Jarvis HOPE Endowment", {}),), (("for Epilepsy Research", {}),)], 18, WHITE,
     anchor=MSO_ANCHOR.MIDDLE, name="Jarvis HOPE Endowment")
text(fx + fw - P - 2.25, ty, 2.25, th, [(("R21-NS133670-02", {}),), (("R01-MH134787-02", {}),)], 17, WHITE,
     anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT, name="Grant numbers")

rx = fx + fw + G
cy = section(rx, yb, rw, hb, "REFERENCES", "References")
draft(rx + P, cy + 0.22, rw - 2 * P, hb - HDR - 0.45, "References", [
    [n(r)] for r in ("Abdulkareem et al., bioRxiv (2026)", "Bragin et al., J. Neurophysiol. (1995)", "Schomburg et al., Neuron (2014)",
                     "Fernández-Ruiz et al., Science (2021)", "Getz et al., J. Neurosci. (2022)", "Tariq et al., Cell Rep. (2022)",
                     "Kloc et al., Hippocampus (2023)", "Farrell et al., Nature (2024)")],
    "References", size=14, space=1)

pres.save(OUT)
print("saved", OUT)
print("left: methods %.2f, biomarkers %.2f | middle: theta %.2f, IED %.2f | right: big picture %.2f, behavior %.2f, slot %.2f"
      % (mh, bh, th_sec, ied_sec, bp_sec, beh_sec, slot_h))
