# -*- coding: utf-8 -*-
"""Build the PTEN behavioral menu.

  python build.py            (miniconda's Python: PyMuPDF)

1. Pulls the report's own figures out of Pten_KO_mosaicism_report_v3.docx (the SVG version of each) and turns them
   into vector PDFs in svgpdf/ (skipped when they are already there).
2. Composes the cover, the read-me page, one page per menu item (content.py) and the synthesis page.
3. Writes the folder in Lab Figures: the merged PDF, each page as PDF and as 300 dpi PNG, the code, and the README.
"""
import glob
import gzip
import os
import re
import shutil
import sys
import zipfile

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E  # noqa: E402
from content import PAGES  # noqa: E402

REPORT = r"C:\Users\Z390\Desktop\jeremystats\Barry Playground\PTEN_Manuscript2_handoff\summary output\Pten_KO_mosaicism_report_v3.docx"
DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\PTEN POSTER\Menus, etc\PTEN_Behavioral_Menu"
NAME = "PTEN_Behavioral_Menu"


# ------------------------------------------------------------------------------------------------ figures
def extract_figures():
    os.makedirs(E.SVG, exist_ok=True)
    z = zipfile.ZipFile(REPORT)
    rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
    target = {}
    for m in re.finditer(r"<Relationship [^>]*>", rels):
        tag = m.group(0)
        i, t = re.search(r'Id="([^"]+)"', tag), re.search(r'Target="([^"]+)"', tag)
        if i and t:
            target[i.group(1)] = t.group(1)
    doc = z.read("word/document.xml").decode("utf-8")
    order = []
    for m in re.finditer(r'r:embed="([^"]+)"', doc):
        t = target.get(m.group(1))
        if t and t not in order:
            order.append(t)
    made = 0
    for i, t in enumerate(order):
        if not t.endswith(".svgz") and not t.endswith(".svg"):
            continue
        out = os.path.join(E.SVG, "%02d.pdf" % i)
        if os.path.exists(out):
            continue
        b = z.read("word/" + t)
        if b[:2] == b"\x1f\x8b":
            b = gzip.decompress(b)
        svg = pymupdf.open(stream=b, filetype="svg")
        pymupdf.open("pdf", svg.convert_to_pdf()).save(out)
        made += 1
    print("figures: %d in the report, %d converted now" % (len(order), made))


# ------------------------------------------------------------------------------------------------ text pages
SHORT = {
    1: "Lo mice learn slowest (21 against 9 sessions); Hi mice learn near the WT rate",
    2: "With the cue no group is impaired; without it both KO groups earn less, and Hi mice collapse at phase 10",
    3: "Only without the cue, and only Hi mice decline with each rotation",
    4: "WT and Lo mice still favor the old place; Hi mice follow the cue",
    5: "Yes, every group remembers it, Hi mice included",
    6: "Lo mice lose the goal at phase 9, Hi mice at phase 10",
    7: "Yes: aim, launch and the shape of the approach match WT",
    8: "No: Hi mice cross the hidden goal at 16.4 against 11.5 cm/s",
    9: "Out in the arena: WT pause more with each rotation, Hi mice less",
    10: "Not without the cue; at former goals they brake like WT",
    11: "WT and Lo check them more each rotation; Hi mice barely do (P 0.003)",
    12: "Removing the cue makes WT pause more and Hi mice pause less (P 0.043)",
    13: "They run: faster without the cue, as many entries, a third of the rewards",
    14: "Hi mice do (they return after a miss); Lo mice do not",
    15: "Hi mice visit the goal as often as WT but stay under the 1.2 s a reward needs",
    16: "Only at the last hidden rotation",
    17: "Only pausing at former goals and total pausing grow apart",
    18: "Twice WT in GCL2 and MML2 of Hi mice; CNO brings GCL2 back",
    19: "Yes at baseline; CNO removes the link",
    20: "Yes at baseline (AUC 0.97), not after CNO",
    21: "Yes: firing falls by three quarters",
    22: "Hidden-goal time rises in KO mice and falls in WT; cued, nothing",
    23: "In GCL2 and MML2; CNO does not reduce them",
    24: "The theta current, not the IED rate",
}


def td(s, extra=""):
    return '<td style="padding:1.5pt 4pt;border-bottom:0.5pt solid #e1e3e8;vertical-align:top;%s">%s</td>' % (extra, E.esc(s))


def cover(doc):
    page = doc.new_page(width=E.PAGE_W, height=E.PAGE_H)
    w = E.PAGE_W - E.ML - E.MR
    y = E.MT
    y += E.draw(page, E.ML, y, w, '<div style="font-size:8.5pt;font-weight:bold;color:%s">%s</div>' % (E.ACCENT, E.KICKER)) + 6
    y += E.draw(page, E.ML, y, w, '<div style="font-size:24pt;font-weight:bold;color:%s">PTEN Behavioral Menu</div>' % E.INK) + 6
    sub = ("The Pten KO mosaicism behavior report (version 3, 24 November 2026), recast one result per page: the question it "
           "answers, a one-sentence answer, panels whose headings state what they show, then how it was measured, what it "
           "shows, how to read it, and its caveats. The figures are the report's own; only their titles were replaced. Page 2 "
           "explains the task, the mice and the words. Exploratory: one number per mouse; P values as the report gives them.")
    y += E.draw(page, E.ML, y, w, '<div style="font-size:9.5pt;font-style:italic;color:%s;line-height:1.3">%s</div>' % (E.MUTED, E.esc(sub))) + 10
    story = ("Mosaic Pten deletion in dentate granule cells gives two phenotypes, not one deficit that grows with dose. Mice "
             "with few KO cells (Lo) are slow to learn the cue rule and lose the goal once it moves, but stop normally when "
             "they reach it. Mice with many KO cells (Hi) learn the cue rule nearly as fast as WT and still remember places, "
             "yet let the cue override place; when the goal is hidden and keeps moving they stop working through the places "
             "that used to pay, run instead, and cross the goal without stopping. Their lower blade carries twice the WT "
             "theta current; silencing the KO cells with CNO brings it back and improves hidden-goal behavior without "
             "reducing the IEDs.")
    y += E.draw(page, E.ML, y, w, '<div style="font-size:9.6pt;color:%s;line-height:1.3"><b>The story in one paragraph.</b> %s</div>'
                % (E.INK, E.esc(story))) + 12
    rows = ['<tr style="font-weight:bold;color:%s">%s%s%s%s%s</tr>' % (
        E.INK, td("#"), td("The question"), td("Results show, in short"), td("Report figure"), td("Page"))]
    for p in PAGES:
        rows.append("<tr>%s%s%s%s%s</tr>" % (td(str(p["num"]), "font-weight:bold"), td(p["question"]), td(SHORT[p["num"]]),
                                             td(p["fig"].replace("Supplementary Figure ", "").replace("Figures", "Figs").replace("Figure", "Fig")),
                                             td(str(p["num"] + 2), "text-align:right")))
    rows.append("<tr>%s%s%s%s%s</tr>" % (td("+", "font-weight:bold"), td("What does it add up to?"),
                                         td("Two phenotypes, one broken step, one lower-blade circuit"), td("Synthesis"),
                                         td(str(len(PAGES) + 3), "text-align:right")))
    table = ('<table style="width:100%%;border-collapse:collapse;font-size:7.4pt;color:%s;line-height:1.22">%s</table>'
             % (E.BODY, "".join(rows)))
    y += E.draw(page, E.ML, y, w, table) + 8
    if y > E.PAGE_H - E.MB:
        raise RuntimeError("the cover table runs into the footer (%.0f pt)" % y)
    E.footer(page, 1)


def section(title, body):
    return ('<p style="font-size:10pt;font-weight:bold;color:%s;margin-bottom:3pt">%s</p>'
            '<p style="font-size:8pt;color:%s;line-height:1.34;margin-bottom:10pt">%s</p>' % (E.INK, E.esc(title), E.BODY, E.esc(body)))


def readme_page(doc):
    page = doc.new_page(width=E.PAGE_W, height=E.PAGE_H)
    y = E.header(page, "READ ME FIRST", "The task, the mice and the words",
                 "What do the mice have to do, who are they, and what do the measures mean?",
                 "A reward needs the mouse to stay still in an unmarked goal zone for 1.2 s; the same mice are tested with "
                 "the goal marked (cued) and unmarked (hidden) as the goal moves three times.")
    gap = 18.0
    cw = (E.PAGE_W - E.ML - E.MR - gap) / 2.0
    left = "".join([
        section("The task",
                "Mice forage in a circular arena for food delivered at an unmarked goal zone, and a reward comes only when the "
                "mouse stays in the zone for 1.2 s. They are first trained with a cue (a beacon on the goal) until they reach "
                "criterion; sessions to criterion measure how fast they learn that the cue predicts reward. Probes follow: "
                "phase 7 at the trained location, then phases 8, 9 and 10, each with the goal moved to a new zone "
                "(anticlockwise in the room view). Every phase has a cued session and, about 32 minutes later, a hidden "
                "session at the same goal. Zone k was the goal of phase k + 6, so the former goals number 0, 1, 2 and 3 across "
                "phases 7 to 10. The cued sessions are the control: same mice, same day, same goal, with the beacon."),
        section("The mice",
                "WT: 19 mice (18 for learning). Pten KO Lo: 5 mice, 3.9 to 9.5% of granule cells KO (M1, M8, M10, M30, M33). "
                "Pten KO Hi: 6 mice, 20.2 to 28.4% (M3, M5, M7, M28, M29, M34). No mouse sits between 9.5% and 20.2%. M27 "
                "and M31 have no histology and enter pooled KO numbers only; Pten;Raptor double KO mice are left out. M6 (WT) "
                "is left out of learning only (27 sessions), M26 (WT) out of the CSD only. IED+ (clear IEDs): M3, M5, M28, M34 "
                "in the behavior cohort, and M13 in the CSD cohort; IED\u2212 means no obvious IEDs, not normal activity. "
                "Heterotopia: M8, M10, M27, M29, M30."),
        section("Marks and statistics",
                "Blue WT, green Lo, red Hi, purple all KO pooled; diamonds IED+, circles IED\u2212 or not recorded. The mouse "
                "is the unit: one number per mouse, then the group test. Between groups: two-sided Mann-Whitney. Within a "
                "group: paired t. Change across phases: each mouse's least-squares slope over phases 7 to 10, compared by "
                "Mann-Whitney. Values are mean \u00b1 SE. P values are given as the report gives them, uncorrected."),
    ])
    right = "".join([
        section("Words used on the pages",
                "Directed run: an approach launched at least 20 cm from the goal (the last stretch heading within 45\u00b0 of "
                "the goal at more than 5 cm/s). Target speed: speed as the mouse enters and moves through the goal zone. "
                "Pause: 1.2 to 10 s below 3 cm/s, away from the wall (the outer band beyond 0.8 of the arena radius is left "
                "out). Former goal: a zone that was the goal of an earlier phase; never-used zone: one that has not been a "
                "goal yet; open interior: more than 2.5 zone radii from the current goal. Slowing ratio: speed in the 1.2 s "
                "after entering the goal divided by speed 1.5 to 0.5 s before (1 = no slowing). Braking event: a fall from a "
                "local speed peak of at least 12 cm/s to below half of it within 1 s. Place pull or latent place preference: "
                "the share of directed runs to a place minus the share to a never-used zone."),
        section("The circuit pages",
                "Theta CSD by layer from depth recordings, at baseline and after CNO. Layers with 1 are the upper "
                "(suprapyramidal) blade, with 2 the lower (infrapyramidal) blade: GCL granule cell layer, MML middle molecular "
                "layer, OML outer molecular layer. CNO acts on hM4D(Gi), the inhibitory DREADD that every KO granule cell "
                "carries (WT mice carry it in about 5% of granule cells). IEDs: interictal epileptiform discharges from the "
                "lab's recording pipeline."),
        section("Where this comes from",
                "Barry Playground/PTEN_Manuscript2_handoff: report_v3.md and Pten_KO_mosaicism_report_v3.docx (2026-11-24). "
                "Every number on these pages is the report's; each page names the report figure it uses. The figures are the "
                "report's own vector graphics, cropped, with their panel titles replaced by statements of what they show."),
    ])
    E.draw(page, E.ML, y, cw, left)
    E.draw(page, E.ML + cw + gap, y, cw, right)
    E.footer(page, 2)


def synthesis(doc, number):
    page = doc.new_page(width=E.PAGE_W, height=E.PAGE_H)
    y = E.header(page, "SYNTHESIS", "What it adds up to",
                 "What does each KO group get wrong, and what links it to the circuit?",
                 "Two phenotypes, not one deficit that grows with dose: Lo mice learn slowly and lose the goal once it moves; Hi "
                 "mice learn the cue, then stop working through the places that used to pay and cross the goal without "
                 "stopping, while their lower blade carries a theta excess that CNO normalizes.")
    w = E.PAGE_W - E.ML - E.MR
    rows = [("", "Pten KO Lo", "Pten KO Hi", "Page"),
            ("Learning the cue rule", "Slowest: 21.2 sessions, every mouse slower than WT", "14.0 sessions, half inside the WT range", "3"),
            ("Place against cue", "Keeps the place (+12.0 points)", "Follows the cue (\u22124.2); the place returns without it", "6, 7"),
            ("Preference for the current goal", "Lost at phase 9", "Lost at phase 10", "8"),
            ("Getting to the goal", "Normal", "Normal", "9"),
            ("Arrival at the hidden goal", "Stops normally", "Crosses it at 16.4 against 11.5 cm/s; 16% of runs rewarded", "10"),
            ("Searching the former goals", "Like WT (+28.8 s per phase)", "Barely (+9.6 against +25.3 s per phase)", "13"),
            ("What they do instead", "Slow and deliberate, badly aimed", "Run faster without the cue", "15"),
            ("Coming back after a miss", "Rarely (2.0% against 8.8%)", "Like WT (10.5%)", "16"),
            ("Theta CSD", "Above WT at GCL2 only", "Twice WT at GCL2 and MML2; CNO brings it back", "20"),
            ("Hidden-goal time after CNO", "Little change (P 0.28)", "Rises (2.4% to 3.7%; P 0.009)", "24")]
    html = []
    for i, r in enumerate(rows):
        style = "font-weight:bold;color:%s" % E.INK if i == 0 else ""
        html.append('<tr style="%s">%s%s%s%s</tr>' % (style, td(r[0], "font-weight:bold"), td(r[1]), td(r[2]),
                                                        td(r[3], "text-align:right")))
    table = ('<table style="width:100%%;border-collapse:collapse;font-size:7.8pt;color:%s;line-height:1.25">%s</table>'
             % (E.BODY, "".join(html)))
    y += E.draw(page, E.ML, y, w, table) + 14
    fits = ("Lo mice have a problem of where to go, with arrival intact: slow to form the cue\u2013reward association, then "
            "lost once the goal moves, coming back rarely and pausing at the wrong zones. Hi mice have a problem of committing, "
            "with knowing roughly where and getting there intact: they return after a miss and brake at old goals, but stop "
            "working through the growing set of former goals, run instead, and cross the goal without the 1.2 s stop. Their "
            "deficit grows with the number of former goals and vanishes with a beacon, the shape of a limit on holding and "
            "testing candidate places (working memory, pattern separation, or both). Their lower blade carries twice the WT "
            "theta current, where the KO cells and their perforant-path synapses sit; that current marks the IED mice, and "
            "CNO normalizes it while hidden-goal behavior improves and the IEDs do not fall. The two KO groups sit on either "
            "side of the 15% line at which LaSarge et al. (2021) saw abnormal activity spread to the network.")
    caveats = ("Five Lo and six Hi mice; single mice move many estimates. % KO, IED status and heterotopia travel together: "
               "every IED+ behavior mouse is Hi, and three of four heterotopia mice with histology are Lo. The key Hi effects "
               "rest on one probe (phase 10), and several measures express the same 1.2 s rule. The dose curves depend on "
               "placing WT at 0% KO. The report notes that M24's phase 9 sessions are dated after its phase 10 sessions.")
    open_q = ("Which result leads: the report itself asks whether the search collapse (pages 11, 13 and 14) is the primary deficit "
              "and the failure to stop at the goal (page 10) its consequence. More Hi mice with behavior before and after "
              "CNO. Histology for M27 and M31, which decides Lo against Hi on learning. A task that varies how similar the goal "
              "locations are, to tell pattern separation from working memory. % KO by blade against theta CSD by blade. The "
              "time from CNO injection to recording. Dentate spike and quantitative IED measures per mouse, to explain the "
              "split within the Hi group.")
    gap = 18.0
    cw = (w - 2 * gap) / 3.0
    for i, (t, b) in enumerate((("How it fits together", fits), ("Caveats across the menu", caveats), ("Open questions", open_q))):
        E.draw(page, E.ML + i * (cw + gap), y, cw, section(t, b))
    E.footer(page, number)


# ------------------------------------------------------------------------------------------------ build
def main():
    extract_figures()
    os.makedirs(os.path.join(DEST, "pages"), exist_ok=True)
    os.makedirs(os.path.join(DEST, "code"), exist_ok=True)
    for f in glob.glob(os.path.join(DEST, "pages", "*")):
        os.remove(f)
    full = pymupdf.open()
    names = []

    def emit(fn, slug):
        d = pymupdf.open()
        fn(d)
        name = "%02d_%s" % (len(names) + 1, slug)
        d.subset_fonts()  # every text box embeds Arial; subsetting takes a page from about 7 MB to under 1 MB
        d.save(os.path.join(DEST, "pages", name + ".pdf"), garbage=4, deflate=True)
        d[0].get_pixmap(dpi=300).save(os.path.join(DEST, "pages", name + ".png"))
        full.insert_pdf(d)
        names.append(name)

    emit(cover, "menu")
    emit(readme_page, "read_me_first")
    for spec in PAGES:
        emit(lambda d, s=spec: E.figure_page(d, s, s["num"] + 2), spec["slug"])
    emit(lambda d: synthesis(d, len(PAGES) + 3), "what_it_adds_up_to")
    full.subset_fonts()
    full.save(os.path.join(DEST, NAME + ".pdf"), garbage=4, deflate=True)
    for f in ("engine.py", "content.py", "build.py", "grid.py", "gaps.py", "hgaps.py"):
        shutil.copy2(os.path.join(HERE, f), os.path.join(DEST, "code", f))
    print("pages:", len(names))
    print("\n".join(names))


if __name__ == "__main__":
    main()
