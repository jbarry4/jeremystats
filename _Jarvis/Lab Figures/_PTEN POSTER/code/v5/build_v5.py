"""PTEN poster v5 (2026-11-27): v4 with every cropped figure redrawn in the poster's look (fig_theta, fig_theta2, fig_behavior,
fig_behavior2, fig_dsx, fig_photos), one group colour scheme, and the KCNT1 poster's funding strip.
PTEN poster v4: Rain's in-progress deck (2026-11-27) with every section filled.

Keeps Rain's header (logos, title, authors, affiliations) and her section set; drops her review comments (answered in
SOURCES), the placeholders and the menu screenshots, and lays out three columns:
  left    Introduction (with the KCNT1 poster's dentate drawing, relabelled for PTEN), Methods, Isolating biomarkers
  middle  Behavior, Theta CSD and chemogenetic silencing
  right   IEDs and dentate spikes: the big picture; Discussion; Funding; References
Every panel carries a letter; each section ends in one figure legend (Rain: "titles ... are for us ... it should be
Figure A through D and then a figure legend"). Type is Aptos (Aptos Display for the title and headings), as on the
KCNT1 poster.

python build_v4.py RAIN.pptx OUT.pptx [measure.json]"""
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from xml.sax.saxutils import escape

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")
V3 = os.path.join(HERE, "data", "v3_media")
E = 914400
GREEN, GOLD, INK, SOFT = "154734", "FFD416", "1E1E1E", "5F6B7A"
MEAS = {}

# ---------------------------------------------------------------- layout grid (inches)
COLS = {"L": (0.5, 15.0), "M": (15.95, 15.55), "R": (31.95, 15.55)}
HB = 3.35                               # header band (Rain's was 5.55)
TOP, BOTTOM, BAND, PAD, GAP = HB + 0.4, 35.5, 1.15, 0.4, 0.45
BODY, LEG, LETTER = 22, 17, 26          # pt: body text, figure legends, panel letters


class Deck:
    def __init__(self):
        self.shapes, self.media, self.nid = [], [], 200

    def id(self):
        self.nid += 1
        return self.nid

    # -------------------------------------------------------------- primitives
    def rect(self, name, x, y, w, h, fill, line=None):
        ln = '<a:ln w="15875"><a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:ln>' % line if line else "<a:ln><a:noFill/></a:ln>"
        self.shapes.append(
            '<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="%d" y="%d"/>'
            '<a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="%s"/>'
            '</a:solidFill>%s</p:spPr><p:txBody><a:bodyPr rtlCol="0" anchor="ctr"/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/></a:p>'
            '</p:txBody></p:sp>' % (self.id(), escape(name), x * E, y * E, w * E, h * E, fill, ln))

    def line(self, name, x0, y0, x1, y1, color="D5DBE2", w_pt=1.25):
        self.shapes.append(
            '<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="%d" name="%s"/><p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr><p:spPr><a:xfrm><a:off x="%d" y="%d"/>'
            '<a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:ln w="%d"><a:solidFill><a:srgbClr val="%s"/>'
            '</a:solidFill></a:ln></p:spPr></p:cxnSp>' % (self.id(), escape(name), x0 * E, y0 * E, max((x1 - x0) * E, 0), max((y1 - y0) * E, 0),
                                                          w_pt * 12700, color))

    def text(self, name, x, y, w, h, paras, anchor="t", autofit=False):
        """paras: list of (runs, align, space_after_pt); runs: list of (text, dict(b, i, sz, color, font))."""
        ps = []
        for runs, algn, spc in paras:
            rr = []
            for t, st in runs:
                font = st.get("font", "Aptos")
                rr.append('<a:r><a:rPr lang="en-US" sz="%d" b="%d" i="%d"%s dirty="0"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
                          '<a:latin typeface="%s"/><a:cs typeface="%s"/></a:rPr><a:t>%s</a:t></a:r>'
                          % (st.get("sz", BODY) * 100, st.get("b", 0), st.get("i", 0), ' baseline="30000"' if st.get("sup") else "",
                             st.get("color", INK), font, font, escape(t)))
            ps.append('<a:p><a:pPr algn="%s"><a:lnSpc><a:spcPct val="%d"/></a:lnSpc><a:spcAft><a:spcPts val="%d"/></a:spcAft></a:pPr>%s</a:p>'
                      % (algn, 96000 if True else 100000, spc * 100, "".join(rr)))
        fit = "<a:spAutoFit/>" if autofit else "<a:noAutofit/>"
        self.shapes.append(
            '<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="%d" y="%d"/>'
            '<a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr><p:txBody>'
            '<a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" anchor="%s">%s</a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>'
            % (self.id(), escape(name), x * E, y * E, w * E, h * E, anchor, fit, "".join(ps)))

    def pic(self, name, path, x, y, w=None, h=None, descr=""):
        """place by width or height (aspect kept); returns (w, h)."""
        path = trimmed(path)
        im = Image.open(path)
        a = im.size[1] / im.size[0]
        if w is None:
            w = h / a
        h = w * a
        rid = "rIdV5_%d" % (len(self.media) + 1)
        ext = os.path.splitext(path)[1].lower()
        self.media.append((rid, path, "image_v5_%02d%s" % (len(self.media) + 1, ext)))
        self.shapes.append(
            '<p:pic><p:nvPicPr><p:cNvPr id="%d" name="%s" descr="%s"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/>'
            '</p:nvPicPr><p:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm>'
            '<a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
            % (self.id(), escape(name), escape(descr or name), rid, x * E, y * E, w * E, h * E))
        return w, h

    # -------------------------------------------------------------- poster pieces
    def card(self, col, y0, y1, title, x=None, w=None):
        cx, cw = COLS[col] if x is None else (x, w)
        self.rect(title + " card", cx, y0, cw, y1 - y0, "FFFFFF")
        self.rect(title + " heading band", cx, y0, cw, BAND, GREEN)
        self.text(title + " heading", cx + 0.4, y0, cw - 0.8, BAND, [([(title.upper(), dict(sz=40, b=1, color="FFFFFF", font="Aptos Display"))], "l", 0)],
                  anchor="ctr")
        return cx + PAD, y0 + BAND + 0.3, cw - 2 * PAD

    def letter(self, ch, x, y):
        self.text("Panel " + ch, x - 0.36, y - 0.08, 0.5, 0.45, [([(ch, dict(sz=LETTER, b=1, color=INK))], "l", 0)])


def trimmed(path, pad=6):
    """the picture cropped to its ink (white margins off), cached beside the figures."""
    import numpy as np
    im = Image.open(path)
    if im.mode == "RGBA" and np.asarray(im)[:, :, 3].min() < 250:
        return path                                    # transparent logos stay as they are
    a = np.asarray(im.convert("RGB"))
    ys, xs = np.where((a < 246).any(axis=2))
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, a.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, a.shape[1])
    if (y0, x0, y1, x1) == (0, 0, a.shape[0], a.shape[1]):
        return path
    d = os.path.join(OUT_DIR, "trimmed")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, os.path.basename(path))
    im.crop((x0, y0, x1, y1)).save(out, dpi=im.info.get("dpi", (300, 300)))
    return out


def fig(name):
    return os.path.join(OUT_DIR, name)


def runs_md(s, sz, color=INK):
    """**bold** spans in a string -> runs."""
    out = []
    for k, part in enumerate(re.split(r"\*\*", s)):
        if part:
            out.append((part.replace("{s}", "*"), dict(sz=sz, b=k % 2, color=color)))     # {s}: a literal star
    return out


def legend(D, name, x, y, w, h, s):
    D.text(name, x, y, w, h, [(runs_md(s, LEG), "l", 0)])


def row(D, items, x, y, w, gap=0.42, hmax=None):
    """items: (letter, png); one height for the row so the widths fill w (or hmax, centred)."""
    items = [(l, trimmed(p)) for l, p in items]
    asp = [Image.open(p).size[0] / Image.open(p).size[1] for _l, p in items]
    h = (w - gap * (len(items) - 1)) / sum(asp)
    if hmax and h > hmax:
        x += (w - gap * (len(items) - 1) - hmax * sum(asp)) / 2
        h = hmax
    xx = x
    for (l, p), a in zip(items, asp):
        D.pic(os.path.basename(p), p, xx, y, h=h)
        if l:
            D.letter(l, xx, y)
        xx += a * h + gap
    return h


def key_runs(sz=LEG):
    """the group colours, as coloured words (the poster's one scheme: grey / pink / magenta)."""
    return [("WT or control ", dict(sz=sz, b=1, color="8C8C8C")), ("●", dict(sz=sz, color="8C8C8C")),
            ("   Lo KO or IED− ", dict(sz=sz, b=1, color="D17FAF")), ("●", dict(sz=sz, color="E7A3C9")),
            ("   Hi KO or IED+ ", dict(sz=sz, b=1, color="A8326E")), ("●", dict(sz=sz, color="A8326E")),
            ("   ◆ IED+ mouse.  ", dict(sz=sz, color=INK))]


def build(D):
    # ================================================================== LEFT
    x, y, w = D.card("L", TOP, 10.9, "Introduction")
    tw = 8.55
    D.text("Introduction text", x, y, tw, 10.9 - y - 0.3, [
        (runs_md("**Interictal epileptiform discharges (IEDs)** mark an epileptic hippocampus. **Dentate spikes (DS)** are normal "
                 "population events of the dentate gyrus, driven by entorhinal input to the granule cells: lateral EC to the outer "
                 "molecular layer (DS1), medial EC to the middle (DS2).", BODY), "l", 10),
        (runs_md("**Mosaic PTEN loss** in dentate granule cells, as in focal cortical dysplasia, makes some mice epileptic and "
                 "leaves others without IEDs, even at similar knockout levels.", BODY), "l", 10),
        (runs_md("**We ask** whether the knockout shows in spatial memory and in the theta current, and whether dentate spikes "
                 "change before IEDs appear: do events between a normal DS and an IED mark the mice that have IEDs?", BODY), "l", 0)])
    D.pic("Dentate gyrus", fig("I_circuit.png"), x + tw + 0.3, y - 0.05, w=w - tw - 0.3)

    y0 = 10.9 + GAP
    y1m = 22.3
    x, y, w = D.card("L", y0, y1m, "Methods")
    pw, ph = D.pic("PTEN pathway", os.path.join(V3, "image4.png"), x, y, h=5.0)
    D.text("Methods text", x + pw + 0.35, y, w - pw - 0.35, 5.2, [
        (runs_md("**PTEN loss** raises PI3K/AKT/mTOR signaling, driving neuronal overgrowth and burst firing.", 20), "l", 7),
        (runs_md("**Mosaic knockout:** at P7, Pten flx/flx mice received a Cre retrovirus in the dentate gyrus; the share of "
                 "infected granule cells (% KO) was counted in histology.", 20), "l", 7),
        (runs_md("**Behavior:** a reward needs 1.2 s in the goal zone; each phase (7–10) moves the goal, with a cued and a "
                 "hidden session (WT 19, Lo KO 5, Hi KO 6 mice).", 20), "l", 7),
        (runs_md("**Recording:** awake, head-fixed; 64-contact probe (20 µm) from CA1 through both blades. 7 controls, "
                 "9 PTEN mice: 5 with IEDs (IED+), 4 without (IED−).", 20), "l", 7),
        (runs_md("**CNO** silences the hM4D(Gi) that every KO granule cell carries.", 20), "l", 0)])
    yy = y + max(ph, 5.2) + 0.3
    h = row(D, [("A", fig("M_headfixed.png")), ("B", fig("X_task.png")), ("C", fig("X_histology.png"))], x, yy, w)
    yy += h + 0.2
    legend(D, "Methods legend", x, yy, w, y1m - yy - 0.25,
           "**A** Head-fixed recording on a wheel; the probe spans CA1 and both dentate blades. **B** One mouse's path in a "
           "cued (goal V1) and a hidden (H1) probe session. **C** Pten KO dentate gyrus: knockout granule cells (red) "
           "concentrate in the lower blade.")

    y0 = y1m + GAP
    x, y, w = D.card("L", y0, BOTTOM, "Isolating biomarkers")
    D.text("Pipeline text", x, y, w, 0.85, [(runs_md("Terabytes of recordings, cataloged on the Vermont Advanced Computing Core (VACC), "
                                                     "went through one custom pipeline:", 20), "l", 0)])
    yy = y + 0.75
    sw = (w - 3 * 0.3) / 4
    for k, (nm, img, txt) in enumerate((("1  Detect", "image10.png", "Two automated detectors flag candidates; their hits are pooled."),
                                         ("2  Curate", "image12.png", "Trained reviewers keep real events and reject artifacts."),
                                         ("3  Align", "image14.png", "Each event's CSD is placed on the layers by its own sinks."),
                                         ("4  Classify", "image16.png", "Amplitude, half-width and fast power sort DS, BTs and IEDs."))):
        xx = x + k * (sw + 0.3)
        D.text("Step " + nm, xx, yy, sw, 0.4, [([(nm, dict(sz=20, b=1, color=GREEN))], "l", 0)])
        _w, hh = D.pic("Step image " + nm, os.path.join(V3, img), xx, yy + 0.42, w=sw)
        D.text("Step text " + nm, xx, yy + 0.5 + hh, sw, 0.9, [([(txt, dict(sz=16, color=INK))], "l", 0)])
    yy += 0.5 + hh + 1.0
    h = row(D, [("A", fig("X_borders.png")), ("B", fig("X_examples.png"))], x, yy, w)
    yy += h + 0.35
    cw, ch = D.pic("IED example", fig("T_ied_example.png"), x, yy, h=BOTTOM - 0.3 - yy)
    D.letter("C", x, yy)
    legend(D, "Biomarkers legend", x + cw + 0.3, yy, w - cw - 0.3, BOTTOM - yy - 0.25,
           "**A** Every event: fast (240–420 Hz) power against amplitude and half-width. DS border: the outline of 2,150 "
           "control DS; IED border: 39 hand-picked IEDs of the five IED+ mice. Inside both or between them: **borderline "
           "transients (BTs)**. **B** One IED+ mouse (m28): a DS, a BT and an IED (LFP, and 240–420 Hz below); the BT and "
           "the IED are briefer than the DS and carry more fast power. **C** One Pten KO IED: voltage by layer, and two "
           "contacts' spectrograms, a pillar of high-frequency power at onset. Thanks to Bennet Fauber for VACC support.")

    # ================================================================== MIDDLE
    y1b = 20.75
    x, y, w = D.card("M", TOP, y1b, "Behavior")
    half = (w - 0.5) / 2
    for k, (lab, png, L) in enumerate((("Goal visible (cued)", "B_cued.png", "A"), ("Goal hidden", "B_hidden.png", "B"))):
        xx = x + k * (half + 0.5)
        D.text("Behavior " + lab, xx, y, half, 0.4, [([(lab, dict(sz=20, b=1, color=GREEN))], "ctr", 0)])
        h = row(D, [(L, fig(png))], xx, y + 0.45, half)
    D.line("Behavior divider A|B", x + half + 0.25, y, x + half + 0.25, y + 0.45 + h)
    yy = y + 0.45 + h + 0.35
    h = row(D, [("C", fig("B_criterion.png")), ("D", fig("B_criterion_ko.png")), ("E", fig("B_oldplace.png")),
                ("F", fig("B_neverused.png")), ("G", fig("B_predicts.png"))], x, yy, w)
    yy += h + 0.35
    h = row(D, [("H", fig("B_former_hidden.png")), ("I", fig("B_former_cued.png")), ("J", fig("B_speed.png"))], x, yy, w)
    yy += h + 0.35
    h = row(D, [("K", fig("B_stay.png")), ("L", fig("B_entries.png")), ("M", fig("B_prev_ko.png")), ("N", fig("B_rpe_ko.png"))], x, yy, w)
    yy += h + 0.2
    D.text("Behavior legend", x, yy, w, y1b - yy - 0.25, [(key_runs() + runs_md(
           "**A–B** One WT, Lo and Hi mouse per phase, cued (A) and hidden (B): grey, the whole session; coloured, the 3 s "
           "before each reward; black dots, rewards; black circle, the current goal. Under each arena: rewards · entries "
           "· s per entry. Right: rewards and time in the goal (mean ± SE; L, H: Lo, Hi against WT, P < 0.05). "
           "Cued, no group is impaired; hidden, both KO groups earn less and Hi mice collapse at phase 10. **C–D** Lo mice "
           "learn the cue rule slowest; % KO does not slow learning. **E–G** Cued phase 8: WT and Lo still run to the old "
           "place (E, filled; open, a never-used zone) and prefer it (F); Hi mice do not; old-place share predicts hidden phase 10 "
           "rewards (G). **H–I** Hi mice fall behind at former goals only when the goal is hidden. **J** At the last hidden "
           "rotation Hi mice run through the reward window. **K–L** Hidden phase 10: Hi mice enter as often as WT but stay "
           "under the 1.2 s a reward needs. **M–N** Time at the previous goal rises with % KO; rewards per entry fall.", LEG),
           "l", 0)])

    x, y, w = D.card("M", y1b + GAP, BOTTOM, "Theta CSD and chemogenetic silencing")
    h = row(D, [("A", fig("T_rasters.png"))], x, y, w)
    yy = y + h + 0.3
    h = row(D, [("B", fig("T_profiles.png")), ("D", fig("T_ied_cno.png"))], x, yy, w)
    yy += h + 0.3
    h = row(D, [("C", fig("T_dreadd.png")), ("E", fig("T_roc.png"))], x, yy, w, hmax=3.2)
    yy += h + 0.15
    legend(D, "Theta legend", x, yy, w, BOTTOM - yy - 0.2,
           "**A** Theta CSD with the LFP traces in a WT, an IED− and an IED+ Pten KO mouse. **B** Theta CSD per layer at "
           "baseline, after CNO and the change (mean ± SE; shaded, the WT hilus, the reference; {s} P < 0.05 against it, {s}{s} also "
           "after Holm): the excess is largest in "
           "IED+ mice at GCL2 and MML2. **C** CNO cuts the firing of hM4D-expressing KO granule neurons. **D** The IED+ mice's "
           "average IED (voltage) starts at GCL2 over MML2, before and after CNO; CNO does not reduce IEDs. **E** MML2 + GCL2 "
           "theta current picks out the IED mice at baseline, not after CNO (right: each mouse; colour = KO level).")

    # ================================================================== RIGHT
    y1d = 26.55
    x, y, w = D.card("R", TOP, y1d, "IEDs and dentate spikes: the big picture")
    h = row(D, [("A", fig("DS_ab.png"))], x, y, w)
    D.letter("B", x, y + h * 2.86 / 5.95)
    yy = y + h + 0.3
    h = row(D, [("C", fig("X_output.png")), ("D", fig("DS_windows.png")), ("E", fig("X_in_time.png"))], x, yy, w)
    yy += h + 0.3
    h = row(D, [("F", fig("X_spectra.png")), ("G", fig("DS_gain.png"))], x, yy, w)
    yy += h + 0.3
    h = row(D, [("H", fig("DS_rates.png"))], x, yy, w)
    D.letter("I", x + w * 9.55 / 14.75, yy)
    yy += h + 0.3
    h = row(D, [("J", fig("X_vs_wt.png")), ("K", fig("DS_cont.png"))], x, yy, w)
    yy += h + 0.2
    legend(D, "DS legend", x, yy, w, y1d - yy - 0.2,
           "One dot per mouse; m7 (24% KO, no IEDs) a diamond; brackets {s} P < 0.05, {s}{s} < 0.01, {s}{s}{s} < 0.001 (exploratory, "
           "uncorrected). **A** The DS sink, its synaptic current, does not change with IED status, knockout level or % KO (only "
           "IED− smaller, P 0.03). **B** The fast (240–420 Hz) power a standard sink produces is higher in IED+ mice. "
           "**C** Output grows with input in every group, from a higher start in IED+ mice. **D** Fast power: ±25 ms around "
           "the DS peak against −170 to −130 ms on the same contact; sink: ±3 ms. **E** Fast power over each "
           "mouse's own baseline: highest for IED+ DS, BTs and IEDs. **F–G** In every dendritic layer the added fast power "
           "is lower in IED− and higher in IED+ mice than in controls. **H** Only IED+ mice make BTs and IED-class events above "
           "the highest control. **I** Calling the IED+ mice: % KO (m7 the miss), DS fast power (in sample) and held-out models. "
           "**J** IED+ DS carry more fast power than control (WT) DS (P 1.9e-05), not more current. **K** Along the continuum "
           "WT DS → IED+ DS → BT → IED, fast gain climbs in every layer.")

    y0 = y1d + GAP
    FUND_H = 1.55
    x, y, w = D.card("R", y0, BOTTOM - FUND_H - 0.3, "Discussion & conclusion", x=COLS["R"][0], w=10.2)
    D.text("Discussion text", x, y, w, BOTTOM - FUND_H - 0.3 - y - 0.2, [
        (runs_md("**1. Place memory.** High-KO mice learn the cue rule and reach the hidden goal, but run through it and drop "
                 "former goals: a hippocampal, not a motor, deficit.", 21), "l", 5),
        (runs_md("**2. Theta.** Lower-blade theta current doubles where KO cells sit, marks the IED mice, and CNO removes it.", 21),
         "l", 5),
        (runs_md("**3. Dentate spikes.** The DS input is unchanged, but its fast-power output rises in IED+ and falls in IED− "
                 "mice; BTs bridge DS and IEDs.", 21), "l", 9),
        (runs_md("**Conclusion.** Mosaic PTEN loss changes what the dentate does with its input, not the input itself. The "
                 "fast power of ordinary dentate spikes may flag IED-prone circuits before IEDs appear.", 21, GREEN), "l", 0)])
    rx = COLS["R"][0] + 10.2 + GAP
    rw = COLS["R"][0] + COLS["R"][1] - rx
    x, y, w = D.card("R", y0, BOTTOM - FUND_H - 0.3, "References", x=rx, w=rw)
    D.text("References text", x, y - 0.05, w, BOTTOM - FUND_H - 0.3 - y, [([(
        "Bragin et al., J Neurophysiol (1995) · Schomburg et al., Neuron (2014) · Fernández-Ruiz et al., Science "
        "(2021) · Getz et al., J Neurosci (2022) · Tariq et al., Cell Rep (2022) · Kloc et al., Hippocampus (2023) "
        "· Farrell et al., Nature (2024) · Abdulkareem et al., bioRxiv (2026)", dict(sz=14, color=INK))], "l", 0)])
    # funding: the KCNT1 poster's strip (the user: "add cooler looking version from the KCNT1 poster"): one dark-green band,
    # the funders' logos in white, the grants beside them
    FY = BOTTOM - FUND_H
    fx, fw = COLS["R"]
    D.rect("Funding strip", fx, FY, fw, FUND_H, GREEN)
    D.text("Funding heading", fx + 0.4, FY, 3.0, FUND_H, [([("FUNDING", dict(sz=32, b=1, color="FFFFFF", font="Aptos Display"))], "l", 0)],
           anchor="ctr")
    lw_p, lh_p = 3.0, 3.0 * 826 / 2305
    D.pic("PTEN Research logo (white)", os.path.join(HERE, "data", "logo_pten_white.png"), fx + 3.35, FY + (FUND_H - lh_p) / 2, w=lw_p)
    lw_n, lh_n = 1.45, 1.45 * 212 / 338
    D.pic("NIH logo (white)", os.path.join(HERE, "data", "logo_nih_white.png"), fx + 6.75, FY + (FUND_H - lh_n) / 2, w=lw_n)
    D.text("Grant numbers", fx + 8.55, FY, fw - 8.75, FUND_H, [
        ([("NIH R21-NS133670-02 · R01-MH134787-02", dict(sz=17, color="FFFFFF"))], "l", 3),
        ([("Jarvis HOPE Endowment for Epilepsy Research", dict(sz=17, color="FFFFFF"))], "l", 0)], anchor="ctr")


def header(sid, x):
    """Rain's header, tightened (the user asked for an efficient header on the KCNT1 poster): logos smaller, a 54 pt title,
    the three affiliations on one line; Aptos."""
    def xf(x, ox, oy, cx=None, cy=None):
        m = re.search(r'<a:off x="(\d+)" y="(\d+)"/><a:ext cx="(\d+)" cy="(\d+)"/>', x)
        cx = int(m.group(3)) if cx is None else int(cx * E)
        cy = int(m.group(4)) if cy is None else int(cy * E)
        return x.replace(m.group(0), '<a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/>' % (ox * E, oy * E, cx, cy))
    if sid == 2:
        return xf(x, 0, 0, 48.0, HB)
    if sid == 3:
        return xf(x, 0.5, 0.2, 1.35 * 5.04 / 2.35, 1.35)
    if sid == 4:
        return xf(x, 0.5, 1.68, 1.45 * 5.19 / 2.55, 1.45)
    if sid == 5:
        return xf(x, 39.6, (HB - 1.54) / 2)
    if sid == 6:
        x = xf(x, 4.1, 0.2, 35.1, 1.75).replace('sz="6000"', 'sz="5400"')
        return x.replace('anchor="ctr"', 'anchor="t"')
    if sid == 7:
        return xf(x, 4.1, 2.05, 35.1, 0.45).replace('sz="3000"', 'sz="2600"')
    if sid == 8:
        x = xf(x, 4.1, 2.62, 35.1, 0.4).replace('sz="2400"', 'sz="1900"')
        sep = ('<a:r><a:rPr sz="1900" b="0" i="0"><a:solidFill><a:srgbClr val="FFD416"/></a:solidFill><a:latin typeface="Calibri"/>'
               '</a:rPr><a:t xml:space="preserve">   </a:t></a:r>')
        return x.replace('</a:p><a:p><a:pPr algn="ctr"/>', sep)
    return x


def main(src, dst):
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(src) as z:
        z.extractall(tmp)
    sp = os.path.join(tmp, "ppt", "slides", "slide1.xml")
    s = open(sp, encoding="utf8").read()
    head, tree_and_tail = s.split("<p:spTree>", 1)
    tree, tail = tree_and_tail.split("</p:spTree>", 1)
    grp = re.match(r"(<p:nvGrpSpPr>.*?</p:grpSpPr>)", tree, re.S).group(1)
    keep = []
    for m in re.finditer(r"<p:(sp|pic)>.*?</p:\1>", tree, re.S):
        sid = int(re.search(r'<p:cNvPr id="(\d+)"', m.group(0)).group(1))
        if sid <= 8:                                           # Rain's header: band, three logos, title, authors, affiliations
            x = header(sid, m.group(0))
            x = x.replace('typeface="Calibri"', 'typeface="Aptos Display"' if sid == 6 else 'typeface="Aptos"')
            keep.append(x)
    D = Deck()
    build(D)
    tail = re.sub(r"<p:extLst><p:ext uri=\"\{6950BFC3[^>]*>.*?</p:ext></p:extLst>", "", tail, flags=re.S)
    s = head + "<p:spTree>" + grp + "".join(keep) + "".join(D.shapes) + "</p:spTree>" + tail
    open(sp, "w", encoding="utf8").write(s)
    # relationships: drop Rain's pictures (except the header logos) and the comments; add ours
    rp = os.path.join(tmp, "ppt", "slides", "_rels", "slide1.xml.rels")
    r = open(rp, encoding="utf8").read()
    used = set(re.findall(r'r:embed="([^"]+)"', "".join(keep)))
    rels = re.findall(r"<Relationship [^>]*/>", r)
    out = []
    for rel in rels:
        rid = re.search(r'Id="([^"]+)"', rel).group(1)
        if "relationships/image" in rel and rid not in used:
            continue
        if "comments" in rel:
            continue
        out.append(rel)
    for rid, path, nm in D.media:
        shutil.copy(path, os.path.join(tmp, "ppt", "media", nm))
        out.append('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                   'Target="../media/%s"/>' % (rid, nm))
    r = re.sub(r"<Relationship [^>]*/>", "", r).replace("</Relationships>", "".join(out) + "</Relationships>")
    open(rp, "w", encoding="utf8").write(r)
    # drop the comments part and media nothing uses
    cdir = os.path.join(tmp, "ppt", "comments")
    if os.path.isdir(cdir):
        shutil.rmtree(cdir)
    ct = os.path.join(tmp, "[Content_Types].xml")
    c = open(ct, encoding="utf8").read()
    c = re.sub(r'<Override PartName="/ppt/comments/[^>]*/>', "", c)
    if 'Extension="png"' not in c:
        c = c.replace("<Default ", '<Default Extension="png" ContentType="image/png"/><Default ', 1)
    open(ct, "w", encoding="utf8").write(c)
    all_rels = "".join(open(os.path.join(dp, f), encoding="utf8").read() for dp, _d, fs in os.walk(tmp) for f in fs if f.endswith(".rels"))
    for f in os.listdir(os.path.join(tmp, "ppt", "media")):
        if "media/" + f not in all_rels:
            os.remove(os.path.join(tmp, "ppt", "media", f))
    if os.path.exists(dst):
        os.remove(dst)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        names = []
        for dp, _d, fs in os.walk(tmp):
            for f in fs:
                names.append(os.path.relpath(os.path.join(dp, f), tmp).replace("\\", "/"))
        names.sort(key=lambda n: (n != "[Content_Types].xml", n))
        for n in names:
            z.write(os.path.join(tmp, n), n)
    shutil.rmtree(tmp)
    print("built", dst, "with", len(D.media), "pictures and", len(D.shapes), "new shapes")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
