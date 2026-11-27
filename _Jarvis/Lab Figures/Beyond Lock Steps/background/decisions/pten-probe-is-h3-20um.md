# pten-probe-is-h3-20um

_PTEN/CTL/DKO linear-probe recordings are H3 (64 ch, 20 um pitch); even contacts are 40 um apart, not 100. csc.compute_csd's 50 um default is wrong for them._

The PTEN-project hippocampal recordings (CTL, PTEN, DKO mice) are on a Cambridge H3: 64 contacts, 20 um apart (backend/app.py "Every recording is read as an H3"; stratasteps uses spacing_um=20). Every-even-contact displays are 40 um apart.

**Why:** Rain's figure v1/v2 (2026-11-19) assumed 50 um pitch and labeled "100 um apart" plus a 500 um bar; the CSD color bars came out 6.25x too small. Caught on 11-20 while adding layers; fixed in v1.1/v2.1 (_Jarvis/Rain Figures/make_rain_figure_x1.py).

**How to apply:** any CSD or depth scale bar for these mice uses 20 um per contact; don't trust `csc.compute_csd(spacing_um=50.0)` or `probes.DUAL_PITCH_UM` defaults for them. See `stratascope-evidence-vs-lab-labels` (a note not copied here) for layer landmarks.
