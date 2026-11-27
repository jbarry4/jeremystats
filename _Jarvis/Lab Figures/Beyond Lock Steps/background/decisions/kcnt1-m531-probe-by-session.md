# kcnt1-m531-probe-by-session

_KCNT1 m531 (2026-07-22): s1 recorded with the H3 Cheetah config and its signal looks linear; s2–s7 used the H10-D config and look H10. Checked 2026-11-20._

KCNT1 m531 (2026-07-22), checked 2026-11-20 because curation of s1 was waiting on "was it an H10?":
- CheetahLogFile.txt names the config that was loaded. s1 used `Cheetah2026-06-01_wheel_H3.cfg`. s2–s7 used `H10_D_open_Cheetah2026-07-21_16-59-03.cfg`. The two configs map CSC numbers to different AD channels: 62 of 64 differ.
- Signal check (300–3000 Hz with the common average removed, correlation by CSC distance):
  - s1 falls off steadily with distance (0.60, 0.43, 0.30, 0.22). That is a single line of contacts.
  - s2–s7 have lag 3 ≥ lag 2, the H10-D's three interleaved columns.
  - s1 re-indexed into the H10 order through AD channels does not match s2 (r = 0.26).
- No session record has `probe` set, so the probe has not been confirmed in Jarvis.

**Why:** the lab wanted this settled before curating m531 s1.

**How to apply:** for "which probe" questions, read the config name in CheetahLogFile.txt first; it is fast and definitive about the channel map. Scripts: scratchpad m531_probe.py / m531_all.py (session-local). Related: [pten-probe-is-h3-20um](pten-probe-is-h3-20um.md).
