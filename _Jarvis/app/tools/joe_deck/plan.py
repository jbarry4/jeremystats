r"""plan.py -- Joe's figures as a Morph deck, slide by slide, written to
plan.json for build.ps1. Every number comes from tab 8 (joe.json) and tab 9
(figs.json); nothing is typed in by hand.

To make the deck again (after tab 8 or 9 changes), from PowerShell:

    python tools\joe_deck\illustrations.py
    python tools\joe_deck\plan.py
    tools\joe_deck\build.ps1 -Plan GUI_logs\.cache\joe_deck\plan.json

The words are in story.py. build.ps1 drives PowerPoint itself (Windows,
Office), so every Morph transition is PowerPoint's own; it reports any text
that does not fit its box and renders every slide to a PNG to look at.

The grammar is the Ferall 2024 deck's:
  * a black title bar (!!T-BG, !!T) that is the section card made small;
  * the figure on a grey stage, zoomed and panned between slides;
  * a light-blue focus box (!!Focus) that glides to where to look;
  * black notes on the right rail: the newest big and red, the older ones
    shrunk to white, each sliding in from off the slide and out again.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFont

APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.join(APP, "GUI_logs", ".cache", "joe_deck")      # what it writes (git-ignored)
FIGS = os.path.join(APP, "GUI_logs", ".cache", "monolith", "joe", "figs")
# Dated by the day it is made: a deck someone has open cannot be written over.
OUT_PPTX = os.path.join(APP, "Joe figures explained %s.pptx" % __import__("time").strftime("%Y-%m-%d"))
sys.path.insert(0, APP)

def _find_fonts():
    """Aptos's files, by their own names: Office keeps them in a cache whose
    file names are hashes. Arial's measures if Aptos is not on this machine
    (the boxes then come out a little roomy; build.ps1 says if one is short)."""
    import glob
    want = {("Aptos", "Regular"): None, ("Aptos", "Bold"): None, ("Aptos", "Display Bold"): None}
    root = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "FontCache")
    for f in glob.glob(os.path.join(root, "*", "CloudFonts", "Aptos*", "*.ttf")):
        try:
            name = ImageFont.truetype(f, 10).getname()
        except OSError:
            continue
        if name in want and want[name] is None:
            want[name] = f
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    return (want[("Aptos", "Regular")] or os.path.join(win, "arial.ttf"),
            want[("Aptos", "Bold")] or os.path.join(win, "arialbd.ttf"),
            want[("Aptos", "Display Bold")] or os.path.join(win, "arialbd.ttf"))


F_REG, F_BOLD, F_DISP_BOLD = _find_fonts()

SW, SH = 960.0, 540.0
STAGE = (14.0, 64.0, 592.0, 532.0)          # where a figure is shown (pt)
STAGE_BG = [236, 236, 236]
RAIL_X, RAIL_W, RAIL_TOP, RAIL_BOT, GAP = 614.0, 334.0, 66.0, 530.0, 9.0
BLACK, WHITE, RED = [0, 0, 0], [255, 255, 255], [255, 0, 0]
BLUE_LINE, BLUE_FILL = [70, 177, 225], [131, 203, 235]
MARGIN = [10, 7, 10, 7]
NEW = {"size": 18.0, "bold": True, "color": RED}
OLD = {"size": 12.0, "bold": False, "color": WHITE}
OFF_X = SW + 30.0
PX_PER_MM = 600 / 25.4


# --------------------------------------------------------------------------
# Measuring text with the real Aptos
# --------------------------------------------------------------------------
_FONTS = {}


def font(bold, size, display=False):
    key = (bold, size, display)
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(F_DISP_BOLD if display else (F_BOLD if bold else F_REG), int(round(size * 10)))
    return _FONTS[key]


def n_lines(text, size, bold, width, display=False):
    f = font(bold, size, display)
    avail = (width - MARGIN[0] - MARGIN[2] - 4) * 10 * 0.94
    n = 0
    for para in text.split("\n"):
        words, line = para.split(" "), ""
        n += 1
        for w in words:
            trial = (line + " " + w).strip()
            if f.getlength(trial) <= avail or not line:
                line = trial
            else:
                n += 1
                line = w
    return n


def text_h(text, size, bold, width):
    return n_lines(text, size, bold, width) * size * 1.24 + MARGIN[1] + MARGIN[3] + 4


# --------------------------------------------------------------------------
# Images, and where a box of one lands on the stage
# --------------------------------------------------------------------------
class Img:
    def __init__(self, name, file, w_mm, h_mm, boxes=None):
        self.name, self.file, self.w, self.h, self.boxes = name, file, w_mm, h_mm, boxes or {}


def fig_img(fid):
    f = os.path.join(FIGS, "fig_%s.png" % fid.replace(".", "_"))
    w, h = Image.open(f).size
    return Img("!!F" + fid.replace(".", "_"), f, w / PX_PER_MM, h / PX_PER_MM)


def view(img, box=None, pad=0.03, stage=STAGE):
    x0, y0, x1, y1 = box or (0, 0, img.w, img.h)
    bw, bh = x1 - x0, y1 - y0
    sx0, sy0, sx1, sy1 = stage
    s = min((sx1 - sx0) / bw, (sy1 - sy0) / bh) * (1 - pad)
    cx, cy = (sx0 + sx1) / 2, (sy0 + sy1) / 2
    return {"img": img, "left": cx - (x0 + bw / 2) * s, "top": cy - (y0 + bh / 2) * s, "s": s, "box": box}


def at(v, box):
    """A box in the image (mm) to slide points, through view v."""
    s = v["s"]
    return [v["left"] + box[0] * s, v["top"] + box[1] * s, (box[2] - box[0]) * s, (box[3] - box[1]) * s]


# --------------------------------------------------------------------------
# The deck
# --------------------------------------------------------------------------
class Deck:
    def __init__(self):
        self.slides = []
        self.notes = []              # the rail now: [{"id", "text", "runs"}], oldest first
        self.n_note = 0
        self.title = ""

    def slide(self, title=None, view_=None, focus=None, focus2=None, note=None, runs=None, clear=False, card=None,
              speaker="", extra=None, keep=None):
        """One slide. `focus` is a box in the image's mm; `note` a new note
        (the newest); `clear` sends the rail's notes out first; `card` makes
        this a section card (the title bar made big)."""
        if title is not None:
            self.title = title
        if clear:
            self.notes = []
        if keep is not None:
            self.notes = self.notes[-keep:] if keep else []
        new_id = None
        if note:
            self.n_note += 1
            new_id = "!!N%d" % self.n_note
            self.notes.append({"id": new_id, "text": note, "runs": runs or []})
        # the rail: the newest big, the rest small; the oldest leave when full
        while True:
            hs = [text_h(n["text"], (NEW if n["id"] == new_id else OLD)["size"], (NEW if n["id"] == new_id else OLD)["bold"], RAIL_W)
                  for n in self.notes]
            if sum(hs) + GAP * (len(hs) - 1) <= RAIL_BOT - RAIL_TOP or len(self.notes) <= 1:
                break
            self.notes.pop(0)
        rail, y = [], RAIL_TOP
        for n, h in zip(self.notes, hs):
            st = NEW if n["id"] == new_id else OLD
            rail.append({"id": n["id"], "text": n["text"], "runs": n["runs"], "top": y, "h": h, "style": st})
            y += h + GAP
        # a zoomed view dims what is around the panel it zooms to
        spot = view_["box"] if view_ is not None and view_.get("box") else None
        self.slides.append({"title": self.title, "view": view_, "focus": focus, "focus2": focus2, "rail": rail,
                            "card": card, "speaker": speaker, "extra": extra or [], "spot": spot})

    # -- shapes --------------------------------------------------------------
    def shapes(self, k):
        S = self.slides[k]
        out = []
        # The title slide has no figure: the stage fills it, and shrinks into place.
        if S["view"] is None and S["card"]:
            out.append(rect("!!Stage", 0, 0, SW, SH, fill=STAGE_BG))
        else:
            out.append(rect("!!Stage", 0, 54, 604, SH - 54, fill=STAGE_BG))
        v = S["view"]
        if v is not None:
            img = v["img"]
            out.append({"kind": "picture", "name": img.name, "file": img.file, "left": v["left"], "top": v["top"],
                        "width": img.w * v["s"], "height": img.h * v["s"], "line": [176, 176, 176], "line_w": 0.75})
        # The spotlight (the Ferall deck's grey): four dim strips round the
        # zoomed panel; with nothing zoomed they fold away to the stage's edges.
        X0, Y0, X1, Y1 = 0.0, 54.0, 604.0, SH
        if v is not None and S["spot"] is not None:
            b = at(v, S["spot"])
            l, t = max(X0, b[0] - 2), max(Y0, b[1] - 2)
            r, bb = min(X1, b[0] + b[2] + 2), min(Y1, b[1] + b[3] + 2)
        else:
            l, t, r, bb = X0, Y0, X1, Y1
        dim = dict(fill=BLACK, fill_t=0.45)
        out.append(rect("!!D1", X0, Y0, X1 - X0, max(0.5, t - Y0), **dim))
        out.append(rect("!!D2", X0, bb, X1 - X0, max(0.5, Y1 - bb), **dim))
        out.append(rect("!!D3", X0, t, max(0.5, l - X0), max(0.5, bb - t), **dim))
        out.append(rect("!!D4", r, t, max(0.5, X1 - r), max(0.5, bb - t), **dim))
        if v is not None:
            for nm, fb in (("!!Focus", S["focus"]), ("!!Focus2", S["focus2"])):
                if fb is not None:
                    b = at(v, fb)
                    out.append(rect(nm, b[0], b[1], b[2], b[3], fill=BLUE_FILL, fill_t=0.63, line=BLUE_LINE, line_w=3.0))
        out.extend(S["extra"])
        out.append(rect("!!Rail", 604, 54, SW - 604, SH - 54, fill=WHITE))
        for r in S["rail"]:
            out.append(note_shape(r["id"], RAIL_X, r["top"], r["h"], r["text"], r["runs"], r["style"]))
        # the off-slide copies: a note arriving next slide waits off the
        # right edge; one that left last slide goes out the same way
        if k + 1 < len(self.slides):
            here = {r["id"] for r in S["rail"]}
            for r in self.slides[k + 1]["rail"]:
                if r["id"] not in here:
                    out.append(note_shape(r["id"], OFF_X, r["top"], r["h"], r["text"], r["runs"], r["style"]))
        if k > 0:
            here = {r["id"] for r in S["rail"]}
            for r in self.slides[k - 1]["rail"]:
                if r["id"] not in here:
                    out.append(note_shape(r["id"], OFF_X, r["top"], r["h"], r["text"], r["runs"], r["style"]))
        out.extend(title_shapes(S["title"], S["card"]))
        return out

    def plan(self):
        return {"width": SW, "height": SH, "duration": 1.5, "out": OUT_PPTX, "png_dir": os.path.join(HERE, "png"),
                "slides": [{"shapes": self.shapes(k), "notes": s["speaker"]} for k, s in enumerate(self.slides)]}


def rect(name, l, t, w, h, fill=None, fill_t=0.0, line=None, line_w=0.0):
    return {"kind": "rect", "name": name, "left": l, "top": t, "width": w, "height": h, "fill": fill, "fill_t": fill_t,
            "line": line, "line_w": line_w}


def note_shape(nid, x, y, h, text, runs, st):
    return {"kind": "snip", "name": nid, "left": x, "top": y, "width": RAIL_W, "height": h, "snip": 0.14, "fill": BLACK,
            "fill_t": 0.0, "line": None, "text": text, "font": "Aptos", "size": st["size"], "bold": st["bold"],
            "color": st["color"], "align": "l", "anchor": "m", "margin": MARGIN, "underline": False,
            "runs": [dict(r, size=None) for r in runs] if st is NEW else [dict(r, color=None, size=None) for r in runs]}


def title_shapes(title, card):
    if card:
        big, sub = card
        txt = big + ("\n" + sub if sub else "")
        runs = [{"start": len(big) + 1, "len": len(sub), "bold": False, "size": 20, "color": None}] if sub else []
        # a word in red, as the Ferall cards have
        red = card_red(big)
        if red:
            i = big.find(red)
            runs.append({"start": i, "len": len(red), "color": RED, "bold": None, "size": None})
        return [{"kind": "snip", "name": "!!T-BG", "left": 150, "top": 150, "width": 660, "height": 240, "snip": 0.16, "fill": BLACK,
                 "fill_t": 0.0, "line": None},
                {"kind": "text", "name": "!!T", "left": 180, "top": 160, "width": 600, "height": 220, "text": txt, "font": "Aptos Display",
                 "size": 40, "bold": True, "underline": False, "color": WHITE, "align": "c", "anchor": "m", "margin": [6, 4, 6, 4],
                 "runs": runs}]
    return [{"kind": "snip", "name": "!!T-BG", "left": -30, "top": 0, "width": SW + 60, "height": 54, "snip": 0.0, "fill": BLACK,
             "fill_t": 0.0, "line": None},
            {"kind": "text", "name": "!!T", "left": 10, "top": 0, "width": 930, "height": 54, "text": title, "font": "Aptos Display",
             "size": 24, "bold": True, "underline": True, "color": WHITE, "align": "l", "anchor": "m", "margin": [6, 2, 6, 2], "runs": []}]


CARD_RED = {}


def card_red(big):
    return CARD_RED.get(big)


# --------------------------------------------------------------------------
# Words
# --------------------------------------------------------------------------
def p_say(p):
    return "P < 0.001" if p < 0.001 else "P = %.3f" % p


def bold_runs(text, *parts):
    runs = []
    for part in parts:
        i = text.find(part)
        if i >= 0:
            runs.append({"start": i, "len": len(part), "bold": True, "color": None, "size": None})
    return runs


def measure_sentence(k, a, b, d):
    hl = "higher" if d > 0 else "lower"
    tail = ": cue − baseline was %s on Precon4 than on Precon1." % hl
    if k == "xlag":
        lead = a if d < 0 else b
        return "The gamma-burst lag between %s and %s moved %.0f ms toward %s leading (cue − baseline, Precon4 against Precon1)." % (a, b, abs(d), lead)
    return {"pli": "Steady-delay coupling, %s with %s (PLI)" % (a, b),
            "icoh": "Coupling with a real delay, %s with %s (imaginary coherence)" % (a, b),
            "gc_ab": "%s predicting %s (Granger %s → %s)" % (a, b, a, b),
            "gc_ba": "%s predicting %s (Granger %s → %s)" % (b, a, b, a),
            "xpeak": "%s and %s gamma bursts rising together (amplitude correlation)" % (a, b),
            "pac_ab": "Theta in %s pacing gamma in %s (PAC)" % (a, b),
            "pac_ba": "Theta in %s pacing gamma in %s (PAC)" % (b, a),
            "pac_aa": "Theta pacing gamma within %s (PAC)" % a,
            "pac_bb": "Theta pacing gamma within %s (PAC)" % b}[k] + tail


FAMILY = {"conduction": "Not just a shared signal", "direction": "Which leads", "amplitude": "Bursts rise together",
          "pac": "Theta paces gamma"}


# --------------------------------------------------------------------------
# The story
# --------------------------------------------------------------------------
def write_outputs(D):
    plan = D.plan()
    # Every slide's words, for reading the deck without PowerPoint.
    with open(os.path.join(HERE, "deck_text.md"), "w", encoding="utf-8") as fh:
        for k, S in enumerate(D.slides):
            v = S["view"]
            fh.write("## Slide %d · %s\n" % (k + 1, S["title"]))
            fh.write("- shows: %s%s\n" % (os.path.basename(v["img"].file) if v else "(no picture)",
                                          "; blue box on %s" % (S["focus"],) if S["focus"] else ""))
            if S["card"]:
                fh.write("- section card: %s / %s\n" % S["card"])
            for r in S["rail"]:
                fh.write("- %s note: %s\n" % ("NEW" if r["style"] is NEW else "old", r["text"]))
            if S["speaker"]:
                fh.write("- speaker notes: %s\n" % S["speaker"])
            fh.write("\n")
    with open(os.path.join(HERE, "plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=0)
    print(len(plan["slides"]), "slides ->", OUT_PPTX)


if __name__ == "__main__":
    # through the imported module, so story.py and this share one copy
    import plan as _plan
    import story
    _plan.write_outputs(story.main())
