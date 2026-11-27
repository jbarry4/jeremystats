// KCNT1 poster, draft 1: 48 x 36 in landscape, styled after the lab's PTEN poster (UVM template v3).
// Images come from draft1_assets (prep_assets.py); every shape carries an objectName so the lab can edit by name.
// pptxgenjs: installed copy if there is one, otherwise the one in this session's scratchpad.
let pptxgen;
try {
  pptxgen = require("pptxgenjs");
} catch (e) {
  pptxgen = require("C:/Users/Z390/AppData/Local/Temp/claude/4f94f33fe0a28c30/"
    + "1f5ba6ec-6196-4d32-a520-c6ea15d8ffc3/scratchpad/deck_b/node_modules/pptxgenjs");
}
const fs = require("fs");
const path = require("path");

const ROOT = "C:/Users/Z390/Desktop/jeremystats/_Jarvis/Lab Figures/KCNT1 POSTER";
const A = path.join(ROOT, "draft1_assets");
const OUT = process.argv[2] || path.join(ROOT, "KCNT1_poster_draft1.pptx");
const SZ = JSON.parse(fs.readFileSync(path.join(A, "sizes.json"), "utf8"));

const C = {
  green: "154734", gold: "FFD416", dgold: "C99A00", ink: "1E1E1E", soft: "5A635E", bg: "EEF1EE",
  white: "FFFFFF", tint: "E6EEE9", frame: "D6DBD8",
};
const F = "Calibri";

const pres = new pptxgen();
pres.defineLayout({ name: "POSTER_48x36", width: 48, height: 36 });
pres.layout = "POSTER_48x36";
pres.theme = { headFontFace: F, bodyFontFace: F };
pres.title = "KCNT1 poster, draft 1";
pres.author = "Barry lab";
const s = pres.addSlide();
s.background = { color: C.bg };

// ---------------------------------------------------------------- helpers
function img(name, x, y, w, objectName) {
  const [pw, ph] = SZ[name];
  const h = (w * ph) / pw;
  s.addImage({ path: path.join(A, name + ".png"), x, y, w, h, objectName: objectName || name });
  return y + h;
}
function rect(x, y, w, h, color, objectName, line) {
  s.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h, fill: { color }, line: line || { type: "none" }, objectName,
  });
}
function card(name, x, y, w, h, heading, band) {
  band = band || 1.1;
  rect(x, y, w, h, C.white, name + " card");
  rect(x, y, w, band, C.green, name + " heading band");
  s.addText(heading, {
    x: x + 0.4, y, w: w - 0.8, h: band, fontFace: F, fontSize: band >= 1.1 ? 38 : 28, bold: true,
    color: C.white, valign: "middle", margin: 0, isTextBox: true, objectName: name + " heading",
  });
}
function sub(letter, text, x, y, w, h, size) {
  s.addText([{ text: letter + "  ", options: { bold: true } }, { text, options: { bold: true } }], {
    x, y, w, h, fontFace: F, fontSize: size || 26, color: C.dgold, valign: "top", margin: 0, isTextBox: true,
    objectName: letter + " subheading",
  });
}
// runs: array of [text, {opts}] or plain strings; a "\n" item breaks the paragraph
function para(runs, x, y, w, h, size, objectName, extra) {
  const parts = [];
  runs.forEach((r) => {
    if (r === "\n") {
      if (parts.length) parts[parts.length - 1].options = Object.assign({}, parts[parts.length - 1].options, { breakLine: true });
      return;
    }
    if (typeof r === "string") parts.push({ text: r, options: {} });
    else parts.push({ text: r[0], options: r[1] || {} });
  });
  s.addText(parts, Object.assign({
    x, y, w, h, fontFace: F, fontSize: size || 19, color: C.ink, valign: "top", margin: 0, isTextBox: true,
    objectName, paraSpaceAfter: 4,
  }, extra || {}));
}
function note(text, x, y, w, h, objectName) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, fill: { color: C.gold }, line: { type: "none" }, rectRadius: 0.08, objectName: objectName + " tag",
  });
  s.addText(text, {
    x, y, w, h, fontFace: F, fontSize: 16, bold: true, color: C.green, align: "center", valign: "middle", margin: 0,
    isTextBox: true, objectName: objectName + " text",
  });
}
const B = (t) => [t, { bold: true }];
const SUP = (t) => [t, { superscript: true }];
const SUB = (t) => [t, { subscript: true }];
const I = (t) => [t, { italic: true }];

// ---------------------------------------------------------------- header
rect(0, 0, 48, 5.6, C.green, "Header band");
img("logo_ecdl", 0.5, 0.3, 5.0, "Lab logo");
img("logo_ngp", 0.5, 2.8, 5.2, "Neuroscience Graduate Program logo");
img("logo_uvm", 39.6, 1.85, 7.9, "UVM Larner logo");
s.addText([
  { text: "A Failing Dentate Gate: Hilar Inhibition Gives Way", options: { breakLine: true } },
  { text: "Before Seizures Spread in KCNT1 Gain-of-Function Mice" },
], {
  x: 6.3, y: 0.2, w: 33.0, h: 2.35, fontFace: F, fontSize: 64, bold: true, color: C.white, align: "center",
  valign: "middle", margin: 0, isTextBox: true, objectName: "Title",
});
para([
  "Shahriar Tafti", SUP("1,2"), ", Angelina Woychosky", SUP("1"), ", Dylan H. Marchand", SUP("1"), ", Eli Rachimi", SUP("1"),
  ", Rain Younger", SUP("1,2"), ", Isabella Piatek", SUP("1"), ", Maddie Massad", SUP("1"), ", Matthew C. Weston", SUP("3"),
  ", Jeremy M. Barry", SUP("1"),
], 6.3, 2.62, 33.0, 0.75, 30, "Authors", { color: C.white, align: "center", valign: "middle" });
para([
  SUP("1"), "Department of Neurological Sciences, Larner College of Medicine, University of Vermont, Burlington, VT", "\n",
  SUP("2"), "Neuroscience Graduate Program, University of Vermont, Burlington, VT", "\n",
  SUP("3"), "Fralin Biomedical Research Institute at Virginia Tech Carilion, Roanoke, VA",
], 6.3, 3.5, 33.0, 1.95, 24, "Affiliations", { color: C.gold, align: "center", paraSpaceAfter: 0 });

// ---------------------------------------------------------------- column 1: introduction
let x = 0.5, w = 14.6, ix = 0.9, iw = 13.8;
card("Introduction", x, 6.0, w, 13.2, "INTRODUCTION");
para([
  I("KCNT1"), " encodes the sodium-activated potassium channel K", SUB("Na"), "1.1 (Slack). Gain-of-function variants cause severe ",
  "developmental and epileptic encephalopathies, from epilepsy of infancy with migrating focal seizures to sleep-related ",
  "hypermotor epilepsy, that rarely respond to current drugs [1, 2].", "\n",
  "Homozygous mice carrying a patient variant (", I("Kcnt1"), " Y777H, human Y796H) have frequent, sleep-related seizures and ",
  "interictal epileptiform discharges (IEDs) that map to motor cortex [3]. The extra K", SUP("+"), " current quiets inhibitory ",
  "neurons, not excitatory ones: in heterozygous mice, SST interneurons fire less while PV interneurons fire more [3, 4].", "\n",
  "The hippocampus has been left out of this picture. We recorded the dentate gyrus, the gate between entorhinal cortex and ",
  "hippocampus, where hilar SST interneurons control what gets through [6].",
], ix, 7.3, iw, 3.1, 20, "Introduction text", { paraSpaceAfter: 6 });
let yb = img("elife_fig4_C", ix, 10.45, 7.4, "SST and PV firing (Shore 2024)");
para([
  B("SST"), " (blue) and ", B("PV"), " (orange) interneurons from heterozygous mice vs WT (black): the same current drives fewer ",
  "spikes in SST cells and more in PV cells. Adapted from Shore et al., eLife 2024, Fig. 4C (CC BY 4.0).",
], ix, yb + 0.06, 7.4, 1.05, 15.5, "SST and PV caption", { color: C.soft });
yb = img("hilar_circuit", 8.75, 10.55, 5.9, "Hilar SST circuit");
para([
  "Hilar SST (HIPP) cells inhibit entorhinal input on granule cell dendrites: lateral entorhinal (LEC) input in the outer, ",
  "medial (MEC) in the middle molecular layer.",
], 8.75, yb + 0.06, 5.9, 1.4, 15.5, "Circuit caption", { color: C.soft });
rect(ix, 17.35, iw, 1.65, C.tint, "Hypothesis box");
para([
  B("Hypothesis. "), "KCNT1 gain of function weakens hilar SST interneurons, the dentate gate on entorhinal input. With the gate ",
  "failing, discharges and seizures start in the hilus and spread, and learning suffers.",
], ix + 0.3, 17.45, iw - 0.6, 1.45, 20, "Hypothesis text", { valign: "middle" });

// ---------------------------------------------------------------- column 1: methods
card("Methods", x, 19.6, w, 15.9, "METHODS");
const yA = img("headfixed", ix, 20.95, 5.1, "Head-fixed recording");
const yB = img("laminar", 6.2, 20.85, 8.5, "Laminar recording");
para([
  B("Recording. "), "Awake, head-fixed ", I("Kcnt1"), " Y777H WT, Het and Hom mice on a treadmill. A 64-contact silicon probe spans CA1 ",
  "and both dentate blades; for optogenetics, an optical fiber sits beside it. Current source density (CSD) maps where current ",
  "enters cells (sinks) and leaves them (sources).",
], ix, Math.max(yA, yB) + 0.08, iw, 0.95, 17, "Recording text");
const yC = img("csd_primer", ix, 25.7, iw, "CSD primer");
para([
  B("Reading the CSD (control mouse). "), "Theta (left) puts sinks in CA1 stratum lacunosum-moleculare and the outer ",
  "molecular layer (OML) for seconds; a dentate spike is a brief sink in the OML (lateral entorhinal input, middle) or the ",
  "middle molecular layer (MML; medial entorhinal input, right) [5].",
], ix, yC + 0.05, iw, 1.05, 17, "CSD primer text");
img("histology", ix, 32.0, 2.6, "Hilus histology");
para([
  B("Optogenetics. "), "SST-Cre × ", I("Kcnt1"), " Y777H mice received Cre-dependent ChR2 (AAV-PHP.eB CAG-DIO-ChR2); the fiber ",
  "delivered 5–12 Hz light. Image: hilus, SST label (green) and NeuN (red).",
], 3.75, 31.95, 4.3, 2.8, 16, "Optogenetics text");
img("arena", 8.4, 32.0, 2.6, "Rotating arena");
para([
  B("Active place avoidance. "), "Mice learn to avoid a shock zone fixed in the room while the floor turns: eight 10-min ",
  "sessions a day for 2 days; 56 mice, young (7–16 weeks) and old (19–46 weeks).",
], 11.15, 31.95, 3.55, 2.8, 16, "Arena text");

// ---------------------------------------------------------------- column 2: where discharges start
x = 15.5; w = 15.8; ix = 15.9; iw = 15.0;
card("Discharges", x, 6.0, w, 14.2, "WHERE DISCHARGES START (2022\u20132025 RECORDINGS)");
sub("A", "IEDs begin as a hilar sink, after hilar units fire and \u03b2\u2013\u03b3 power rises", ix, 7.25, iw, 0.6);
yb = img("ied_hilus", ix, 7.95, 5.3, "IED from the hilus");
para([
  "One IED in a KCNT1 mouse. ", B("Top: "), "CSD with the LFP overlaid; the first sink is in the hilus, then CA1 and cortex ",
  "follow (right, probe track). ", B("Bottom: "), "before the IED, hilar LFP carries \u03b2\u2013\u03b3 power that CA1 lacks, and ",
  "hilar units (300\u20136000 Hz) fire.",
], ix, yb + 0.08, 5.3, 20.05 - yb - 0.08, 15, "A caption");
const rx = 21.45, rw = 9.45;
sub("B", "A KCNT1 discharge is two dentate spikes; KCNT1 dentate spikes hit OML and MML at once", rx, 7.95, rw, 1.0, 24);
yb = img("ied_two_ds", rx, 9.0, rw, "Two-DS discharge");
para([
  B("Left: "), "a discharge in two steps: a sink at the OML and hilus (red arrow), then ~5 ms later sinks at OML and MML ",
  "together (blue arrow) and a ~600 ms deflection. ", B("Right: "), "a KCNT1 dentate spike, larger than in controls and again ",
  "with OML and MML sinks at once; a control DS uses one or the other (Methods).",
], rx, yb + 0.06, rw, 1.45, 15, "B caption");
sub("C", "Under urethane, Hom mice show IEDs that WT mice rarely do", rx, 15.15, rw, 0.95, 24);
yb = img("urethane", rx, 16.1, 4.55, "Urethane IED rate");
para([
  "Confirmed IEDs per minute in 128-channel recordings (hippocampus and secondary motor cortex) under urethane, 2022; ",
  "one point per mouse, lines at medians. Four of five WT had none. Hom vs WT, Mann\u2013Whitney P = 0.003.",
], rx + 4.7, 16.15, rw - 4.7, 3.9, 15, "C caption");

// ---------------------------------------------------------------- column 2: seizure onset
card("Seizure", x, 20.6, w, 14.9, "SEIZURE ONSET");
sub("D", "The seizure starts in the hilus as a hilar interneuron falls silent, then recruits both blades and CA1", ix, 21.85, iw, 1.0);
yb = img("seizure", ix, 22.9, iw, "m459 seizure origin");
para([
  "Spontaneous seizure in awake Hom mouse 459 (one of the six old Hom in F). ", B("Top: "), "where the discharge is at each ",
  "stage. ", B("Middle: "), "CSD with the LFP overlaid; the hilar interneuron (channel 41) fired at about 3\u00d7 its baseline for ",
  "3 s before onset, then fell silent for over 80 s. ", B("Bottom: "), "each zone's current relative to its own baseline. One ",
  "opportunistic seizure; no claims about seizure rate.",
], ix, yb + 0.06, iw, 35.4 - yb - 0.06, 15, "D caption");

// ---------------------------------------------------------------- column 3: SST optogenetics
x = 31.7; w = 15.8; ix = 32.1; iw = 15.0;
card("Optogenetics", x, 6.0, w, 9.55, "SST OPTOGENETICS");
note("2024 example \u00b7 Jeremy's new examples to add", 40.4, 6.32, 6.75, 0.46, "Opto note");
sub("E", "Light-driven SST interneurons follow theta rhythms; at 7 Hz, dentate spikes fall into step and IEDs thin out", ix, 7.25, iw, 1.0, 24);
const yE1 = img("opto_csd", ix, 8.35, 8.7, "7 Hz CSD");
const yE2 = img("opto_autocorr", 41.0, 8.3, 6.1, "SST unit entrainment");
para([
  "CSD 5 s before and 5 s during 7 Hz light in a ", I("Kcnt1"), " Y777H mouse expressing ChR2 in SST cells; bottom row, ",
  "spikes of a light-driven unit (putative hilar SST interneuron). One example.",
], ix, yE1 + 0.05, 8.7, 15.45 - yE1 - 0.05, 15, "E left caption");
para([
  "The unit's autocorrelation and spectrum at each light frequency: rhythmic power peaks at 5 Hz and fades at 12 Hz.",
], 41.0, yE2 + 0.05, 6.1, 15.45 - yE2 - 0.05, 15, "E right caption");

// ---------------------------------------------------------------- column 3: behavior
card("Behavior", x, 15.95, w, 13.1, "BEHAVIOR");
sub("F", "Old Hom mice fail to improve overnight in active place avoidance", ix, 17.2, iw, 0.6);
yb = img("behavior", ix, 17.9, iw, "Behavior figure");
para([
  "All 56 mice (4 robust-rule outliers ringed in c). Old Hom improved less than old WT from day 1 to day 2 (Yuen's ",
  "trimmed-mean test P = 0.002; Poisson GEE rate ratio 2.10, 95% CI 1.05\u20134.19, P = 0.036); young Hom and Het did not ",
  "differ from WT. Shocks counted per floor turn (floor speed varied between cohorts); 4 sessions with shock faults ",
  "excluded. Exploratory; P values uncorrected.",
], ix, yb + 0.05, iw, 29.0 - yb - 0.05, 15, "F caption");

// ---------------------------------------------------------------- column 3: conclusions, acknowledgments, references
card("Conclusions", x, 29.45, w, 3.6, "CONCLUSIONS", 0.85);
para([
  B("1. Discharges start in the hilus. "), "The first sink of an IED and of a seizure lies in the hilus; the blades and CA1 follow.", "\n",
  B("2. Hilar inhibition gives way first. "), "A hilar interneuron fired at 3\u00d7 baseline, then fell silent as the seizure began.", "\n",
  B("3. SST interneurons are a lever. "), "Driven by light, they follow theta rhythms, and at 7 Hz IEDs thinned.", "\n",
  B("4. Learning suffers with age. "), "Old Hom mice fail to improve overnight; young Hom and Het learn like WT.", "\n",
  B("Next: "), "SST and PV optogenetic rescue during discharges and learning, in larger cohorts with WT controls.",
], ix, 30.42, iw, 2.55, 17, "Conclusions text", { paraSpaceAfter: 3 });
card("Acknowledgments", x, 33.45, 7.75, 2.05, "ACKNOWLEDGMENTS", 0.7);
para([
  "We thank Dr. William Tobin for advice on head fixation and viral injections and for ", I("Kcnt1"), " Y777H mice, Allyson ",
  "Turner for help with head-fixation surgery, and Dr. Amy Shore and Dr. Wayne Frankel, in whose laboratory the line ",
  "was developed.",
], ix, 34.22, 7.15, 0.95, 13, "Acknowledgments text");
note("Funding to confirm", ix, 35.05, 3.0, 0.36, "Funding note");
card("References", 39.75, 33.45, 7.75, 2.05, "REFERENCES", 0.7);
para([
  "[1] Barcia et al., Nat. Genet. (2012)  [2] Heron et al., Nat. Genet. (2012)", "\n",
  "[3] Shore et al., Cell Rep. (2020)  [4] Shore et al., eLife (2024)", "\n",
  "[5] Bragin et al., J. Neurophysiol. (1995)  [6] Yuan et al., eLife (2017)",
], 40.15, 34.25, 7.15, 1.15, 13.5, "References text", { paraSpaceAfter: 2 });

pres.writeFile({ fileName: OUT }).then((f) => console.log("wrote", f));
