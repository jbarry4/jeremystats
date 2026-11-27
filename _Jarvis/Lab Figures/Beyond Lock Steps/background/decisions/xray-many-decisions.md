# xray-many-decisions

_X-ray Many + Novocaine (asked 2026-11-07): folders of Verified DS 5%/10% sets, per-recording box on each average CSD, ΔBIC+10% separation, versioned bundles, Novocaine liminal space later._

The user asked for X-ray (web/js/dspca.js, backend/dspca.py) to get a **Many** mode. Asked and answered on 2026-11-07.

**What the Many holds**
- Folders of recording sets. The first two are "Verified DS 5%" and "Verified DS 10%". Each covers the 18 v2 recordings (see [rootcanal-workflow-decisions](rootcanal-workflow-decisions.md)).
- Each recording's events are the ones inside the workflow's DS border. These come from workflow runs, not from a bank entry version:
  - "Verified DS 5% · CTL & PTEN v2" (df8f89c45c34)
  - "Verified DS 10% · CTL & PTEN v2" (f7e3cb9cee38)
  - Both draw the border around CTL Baseline v2 and apply it to CTL & PTEN Baseline v2.
- Global parameters are set once.

**How each recording is run**
- The box goes on each recording's own **average-CSD tile**: drag depth and time, or click one time sample. There is no global depth band.
- Recordings run one at a time or all together. Results show in Single, and they reopen from the Many run set.

**What each result reports**
- Separation possible: yes / weak / no, from two-vs-one ΔBIC on the X-ray features AND the smaller class holding at least 10% of the events.
- Sink strength.

**Where results go**
- Each X-ray result is saved as a versioned artifact bundle tied to the Event Bank, like Root Canal's saved singles.

**X-ray Single**
- Everything already processed should show.
- Version selection uses the git-style version tree (BARRY.ui.versionTree), not radio buttons.

**Novocaine**
- The liminal space the X-ray bundles go to for full extraction, modelled on Drift's Monolith artifacts.
- The user chose the name "Novocaine".
- Prepare it, but **wait for the user to say "extract"** before moving any bundles in.

**Why:** DS1/DS2 typing across the PTEN/CTL baseline, before the final analysis.

**2026-11-10:** the liminal space was built as **The Extraction Room**. It is the sixth and last Dentist step and has its own page, web/extraction.html. Novocaine was its first name, so bundles still carry the `novocaine` key.
- backend/extraction.py, artifact kind `extraction`, one per room. Each extraction is a new version.
- First tab: Dentate Spike. It shows class-mean CSD, depth profiles, a mean sink/mean source switch, the delta in sink mode, and a %KO chip.
- %KO lives in the shared pref `extraction_ko`, seeded from the JB % hits sheet. Controls are 0.
- v1 holds the 18 Verified DS 5% bundles.
- "Toggle the label" means the separable / not separable call, not DS1/DS2. I misread it once.
- The call goes in the shared pref `extraction_sep` (yes/no over X-ray's verdict).
- Separability stats:
  - PTEN vs CTL: Fisher.
  - CTL / Low / High: Freeman–Halton.
  - %KO: Mann–Whitney.
- A DS1↔DS2 swap (`extraction_flip`) also exists.

**How to apply:** the folders reuse the Root Canal folder and archive prefs patterns with BARRY.prefs.mergeKey. Never move bundles into Novocaine unasked.
