"""PTEN poster v4: panels taken from the menus' vector page PDFs (and the lab's opening figure), below their panel
headings so the headings' words move into the poster's captions. Each crop is rendered at 450 dpi and trimmed to its
ink; masks (page points) paint over leftovers such as stray P values. Nothing in a plot is changed."""
import os
import fitz
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MEN = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\PTEN POSTER\Menus, etc"
BM = os.path.join(MEN, "PTEN_Behavioral_Menu", "pages")
JM = os.path.join(MEN, "Jeremy_Menu_TightLayers_112726", "pages")
FU = os.path.join(MEN, "Jeremy_Menu_Followup_112526", "pages")
DS = os.path.join(MEN, "DS_Story_Menu_112326", "pages")
OPEN = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources\Opening4paperAndPoster.pdf"
DPI = 450

# name: (pdf, [x0, y0, x1, y1] in points, masks [[x0, y0, x1, y1], ...])
CROPS = {
    # behavior
    "B_cued_runs":    (os.path.join(BM, "04_the_task_and_the_session_measures.pdf"), [78, 151, 334, 341], []),
    "B_hidden_runs":  (os.path.join(BM, "04_the_task_and_the_session_measures.pdf"), [78, 364, 334, 572], []),
    "B_cued_meas":    (os.path.join(BM, "04_the_task_and_the_session_measures.pdf"), [336, 163, 437, 341], []),
    "B_hidden_meas":  (os.path.join(BM, "04_the_task_and_the_session_measures.pdf"), [336, 386, 437, 572], []),
    "B_criterion":    (os.path.join(BM, "03_learning_the_cue_rule.pdf"), [41, 178, 222, 335], []),
    "B_criterion_ko": (os.path.join(BM, "03_learning_the_cue_rule.pdf"), [222, 167, 420, 335], []),
    "B_oldplace":     (os.path.join(BM, "06_cue_against_place.pdf"), [41, 182, 234, 362], []),
    "B_neverused":    (os.path.join(BM, "06_cue_against_place.pdf"), [236, 171, 420, 362], []),
    "B_predicts":     (os.path.join(BM, "06_cue_against_place.pdf"), [133, 397, 330, 565], []),
    "B_former_hidden": (os.path.join(BM, "13_the_set_to_rule_out.pdf"), [60, 192, 380, 422], []),
    "B_former_cued":  (os.path.join(BM, "13_the_set_to_rule_out.pdf"), [60, 470, 380, 705], []),
    "B_speed":        (os.path.join(BM, "10_arriving_at_the_goal.pdf"), [41, 411, 420, 610], []),
    "B_stay":         (os.path.join(BM, "17_last_rotation_zones.pdf"), [264, 181, 416, 322], []),
    "B_entries":      (os.path.join(BM, "17_last_rotation_zones.pdf"), [418, 171, 572, 322], []),
    "B_prev_ko":      (os.path.join(BM, "17_last_rotation_zones.pdf"), [41, 344, 298, 505], []),
    "B_rpe_ko":       (os.path.join(BM, "17_last_rotation_zones.pdf"), [300, 344, 572, 505], []),
    # theta and CNO
    "T_rasters":      (OPEN, [3, 148, 606, 290], [[3, 148, 17, 163]]),
    "T_profiles":     (os.path.join(BM, "20_theta_csd_by_layer.pdf"), [128, 362, 482, 566], []),
    "T_roc":          (os.path.join(BM, "22_theta_csd_marks_the_ied_mice.pdf"), [134, 151, 470, 283], []),
    "T_dreadd":       (os.path.join(BM, "23_the_dreadd_works.pdf"), [319, 172, 522, 302], []),
    "T_ied_cno":      (os.path.join(BM, "25_interictal_discharges.pdf"), [41, 161, 425, 304], []),
    # methods
    "M_task":         (OPEN, [0, 0, 226, 126], [[0, 0, 14, 16]]),
    "M_histology":    (OPEN, [420, 306, 592, 436], []),
    "M_ied_example":  (OPEN, [0, 290, 415, 440], [[0, 288, 13, 304], [246, 288, 262, 304]]),
    # dentate spikes
    "D_output":       (os.path.join(JM, "02_q1_synaptic_efficacy.pdf"), [28, 490, 226, 705], []),
    "D_spectra":      (os.path.join(JM, "05_q4_dominant_frequency.pdf"), [28, 161, 402, 276], []),
    "D_borders":      (os.path.join(JM, "08b_q7_supp_classes_and_q4.pdf"), [28, 148, 345, 317], []),
    "D_vs_wt":        (os.path.join(JM, "08b_q7_supp_classes_and_q4.pdf"), [28, 414, 560, 596], [[102, 438, 167, 448], [306, 438, 347, 448], [468, 438, 509, 448]]),
    "D_examples":     (os.path.join(DS, "02_primer.pdf"), [28, 373, 420, 532], []),
    "D_in_time":      (os.path.join(FU, "03_when_fast_power_is_measured.pdf"), [34, 418, 301, 598], []),
}


def stray_marks(pdf, rect, words):
    """masks over these exact words inside the crop (e.g. the '.030' and '.002' above 'Goal hidden')."""
    p = fitz.open(pdf)[0]
    out = []
    for w in p.get_text("words"):
        if w[4] in words and rect[0] <= w[0] <= rect[2] and rect[1] <= w[1] <= rect[3]:
            out.append([w[0] - 0.5, w[1] - 0.5, w[2] + 0.5, w[3] + 0.5])
    return out


# the user: "remove the weird placement of the .030 or .002 under Goal hidden": both crops start below their titles and
# those two P values (the poster names the panels); the former-goals counts stay


def render(name, pdf, rect, masks, pad_px=12):
    p = fitz.open(pdf)[0]
    for m in masks:
        p.draw_rect(fitz.Rect(*m), color=None, fill=(1, 1, 1), overlay=True)
    pix = p.get_pixmap(clip=fitz.Rect(*rect), dpi=DPI, alpha=False)
    im = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    ink = (im < 235).any(axis=2)
    ys, xs = np.where(ink)
    y0, y1 = max(ys.min() - pad_px, 0), min(ys.max() + pad_px, im.shape[0])
    x0, x1 = max(xs.min() - pad_px, 0), min(xs.max() + pad_px, im.shape[1])
    Image.fromarray(im[y0:y1, x0:x1]).save(os.path.join(HERE, "out", "crop_%s.png" % name), dpi=(DPI, DPI))
    return (x1 - x0) / DPI, (y1 - y0) / DPI


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    for k, (pdf, rect, masks) in CROPS.items():
        w, h = render(k, pdf, rect, masks)
        print("%-16s %.2f x %.2f in at 100%%, masks %d" % (k, w, h, len(masks)))
