"""The "JeremyDraft" decks (2026-11-27): every prose box on the KCNT1 (v11) and PTEN (v6) posters is replaced by a
placeholder for Jeremy to write himself: "WRITE NON-AI SLOP regarding [a vague recap of what the box said]".

Each box stays where it is, with its own font, size, colour and paragraph spacing (the first plain run of each
paragraph lends its formatting). Bold lead-in labels such as "Hypothesis." or "1. Learning suffers with age." are kept,
and so is the behavior legend's colour key. Titles, authors, section headings, references, grants and
acknowledgments are left alone.

  python jeremy_draft.py"""
import os
import re
import zipfile
from xml.sax.saxutils import escape

LF = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures"
P = "WRITE NON-AI SLOP regarding "

PTEN = {
    "Introduction text": ["[what IEDs and dentate spikes are, and the entorhinal inputs behind dentate spikes]",
                          "[mosaic PTEN loss: some knockout mice get IEDs and others don't]",
                          "[the questions: memory, theta, and whether dentate spikes change before IEDs show up]"],
    "Methods text": ["[what PTEN loss does to neurons]",
                     "[how the mosaic knockout was made and how % KO was counted]",
                     "[the place task and the group sizes]",
                     "[the head-fixed probe recordings and the mouse groups]",
                     "[silencing the knockout cells with CNO]"],
    "Methods legend": ["[the recording setup, example arena paths and the knockout histology]"],
    "Pipeline text": ["[how much data there was, the VACC and the pipeline]"],
    "Step text 1  Detect": ["[finding candidate events]"],
    "Step text 2  Curate": ["[reviewers checking the events by hand]"],
    "Step text 3  Align": ["[lining each event up on the layers]"],
    "Step text 4  Classify": ["[sorting DS, BTs and IEDs]"],
    "Biomarkers legend": ["[how DS, BTs and IEDs are told apart, an example of each, and the IED example]"],
    "Behavior legend": [("keep_until", "A\u2013B",
                         "[the example sessions, learning the rule, the old-place preference, former goals, speed at the goal "
                         "and the % KO trends]")],
    "Theta legend": ["[the theta CSD rasters, the layer profiles with CNO, the DREADD check, IED onset with CNO, and picking out "
                     "IED mice from theta]"],
    "DS legend": ["[the DS sink and fast power by group and by % KO, the time windows used, and the DS-to-IED continuum]"],
    "Discussion text": ["[what the behavior says about place memory]",
                        "[what the theta current says]",
                        "[what the dentate spikes say]",
                        "[the overall takeaway]"],
}

KCNT1 = {
    "Introduction text": ["[KCNT1 gain of function and the epilepsy it causes]",
                          "[the Y777H mouse and what happens to its interneurons]",
                          "[why we looked at the hippocampus and the dentate]"],
    "SST and PV caption": ["[the redrawn SST and PV firing data]"],
    "Circuit caption": ["[the dentate circuit: its inputs and the SST and PV cells]"],
    "Hypothesis text": ["[the hypothesis]"],
    "Recording text": ["[the recording setup and how to read a CSD]"],
    "CSD primer text": ["[the example dentate spike against the example IED]"],
    "Optogenetics text": ["[the SST ChR2 setup and the histology]"],
    "Arena text": ["[the active place avoidance task and the cohort]"],
    "A subheading": ["[where IEDs start]"],
    "A caption": ["[the example IED and the activity before it]"],
    "B subheading": ["[the two-step discharge and the KCNT1 dentate spike]"],
    "B caption": ["[the two discharge steps and the dentate spike profile]"],
    "C subheading": ["[urethane IEDs]"],
    "C caption": ["[IED rates per mouse and the stats]"],
    "D subheading": ["[how the seizure starts and spreads]"],
    "D caption": ["[the mouse 459 seizure stage by stage and the hilar interneuron]"],
    "E subheading": ["[the SST unit following the light]"],
    "E left caption": ["[the light-driven SST unit and how it follows each light frequency]"],
    "F subheading": ["[overnight learning in old Hom mice]"],
    "F caption": ["[overnight improvement by genotype and age, and the stats]"],
    "Conclusions text": ["[learning and age]",
                         "[where discharges start]",
                         "[the hilar interneuron before the seizure]",
                         "[SST entrainment by light frequency]",
                         "[the next experiments]"],
}

RUN = re.compile(r"<a:r>.*?</a:r>", re.S)


def run_text(r):
    m = re.search(r"<a:t[^>]*>(.*?)</a:t>", r, re.S)
    return m.group(1) if m else ""


def is_bold(r):
    return re.search(r'<a:rPr[^>]*\bb="1"', r) is not None


def plain_rpr(runs):
    """the formatting of the first non-bold run (else the first run, unbolded)."""
    src = next((r for r in runs if not is_bold(r)), None)
    m = re.search(r"<a:rPr[^>]*/>|<a:rPr[^>]*[^/]>.*?</a:rPr>", src or runs[0], re.S)
    if not m:
        return "<a:rPr/>"
    return m.group(0)                                           # an all-bold paragraph (a subheading) stays bold


def new_para(p, spec):
    runs = RUN.findall(p)
    ppr = re.search(r"<a:pPr[^>]*/>|<a:pPr[^>]*[^/]>.*?</a:pPr>", p, re.S)
    end = re.search(r"<a:endParaRPr[^>]*/>|<a:endParaRPr[^>]*[^/]>.*?</a:endParaRPr>", p, re.S)
    keep = []
    if isinstance(spec, tuple):                                 # keep every run before the one that starts with `until`
        _k, until, text = spec
        for r in runs:
            if run_text(r).startswith(until):
                break
            keep.append(r)
    else:
        text = spec
        lead = run_text(runs[0]).strip() if runs else ""
        if (runs and is_bold(runs[0]) and len(lead) > 2 and lead[-1] in ".:" and lead != "Left:"
                and len(runs) > 1):                             # a bold lead-in label ("Hypothesis.", "Behavior:")
            keep.append(runs[0])
            if not run_text(runs[0]).endswith(" "):
                keep[-1] = keep[-1].replace("</a:t>", " </a:t>").replace("<a:t>", '<a:t xml:space="preserve">', 1)
    rpr = plain_rpr(runs)
    body = "".join(keep) + "<a:r>%s<a:t>%s</a:t></a:r>" % (rpr, escape(P + text))
    return "<a:p>%s%s%s</a:p>" % (ppr.group(0) if ppr else "", body, end.group(0) if end else "")


def draft(src, dst, table):
    zin = zipfile.ZipFile(src)
    s = zin.read("ppt/slides/slide1.xml").decode("utf8")
    done = set()

    def fix_sp(m):
        sp = m.group(0)
        nm = re.search(r'<p:cNvPr [^>]*name="([^"]*)"', sp).group(1)
        if nm not in table:
            return sp
        specs = list(table[nm])
        paras = re.findall(r"<a:p>.*?</a:p>", sp, re.S)
        full = [p for p in paras if "".join(run_text(r) for r in RUN.findall(p)).strip()]
        assert len(full) == len(specs), (nm, len(full), len(specs))
        it = iter(specs)
        out = sp
        for p in full:
            out = out.replace(p, new_para(p, next(it)), 1)
        done.add(nm)
        return out

    s = re.sub(r"<p:sp>.*?</p:sp>", fix_sp, s, flags=re.S)
    missing = set(table) - done
    assert not missing, missing
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for it in zin.infolist():
            data = s.encode("utf8") if it.filename == "ppt/slides/slide1.xml" else zin.read(it.filename)
            z.writestr(it, data)
    print("wrote", dst, "-", len(done), "boxes")


if __name__ == "__main__":
    draft(os.path.join(LF, "_PTEN POSTER", "PTEN_poster_v6.pptx"), os.path.join(LF, "_PTEN POSTER", "PTEN_poster_JeremyDraft.pptx"), PTEN)
    draft(os.path.join(LF, "_KCNT1 POSTER", "KCNT1_poster_v11.pptx"), os.path.join(LF, "_KCNT1 POSTER", "KCNT1_poster_JeremyDraft.pptx"), KCNT1)
