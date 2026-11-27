# Beyond Lock Steps

Everything done to the PTEN dentate spike (DS) data after Lock, written down so another Claude Code session (the user's
home laptop) can verify the PTEN work and run the same pipeline on the KCNT1 data. Packed 2026-11-27 on the lab PC
(Bluebarry). Code and notes are here, in git; the data is on the netfiles share.

## Read in this order

1. **This file**: what is where, the rules, the first tasks.
2. **PIPELINE_PTEN.md**: the eight steps from Lock to the menus, with ids, settings, scripts and outputs.
3. **VERIFY_PTEN.md**: the numbers a rerun must reproduce at each stage.
4. **KCNT1_PLAN.md**: the user's decisions for KCNT1, what to ask the user first, and the steps.
5. As needed: **OUTPUTS_INDEX.md** (where every PTEN output is), **PATHS.md** (every hard-coded path in the code),
   **code/SCRIPTS.md** (every script with its own one-line description), **background/decisions/INDEX.md** (the work PC's
   notes on each decision and the reasons behind it).

## What is in this folder

| path | what |
|---|---|
| `code/battery/` | the frozen test battery's code and its own README.md and METHODS.md (from `Desktop\DS_PTEN_figures_2026-11-16\battery`) |
| `code/pipeline_scratch/` | the session's analysis scripts: dedupe and m1 repair, Root Canal and room rebuilds, deep round, filter and before / after reads, battery runs (`run5.sh`, `strict_all.sh`), ML drivers |
| `code/menus/` | DS story menu, Jeremy menu, follow-up, supplements, layer check, poster figures |
| `code/poster/` | the PTEN poster build |
| `background/decisions/` | 56 decision notes from the work PC's Claude memory, with Drive ids and links taken out |

Only text is here. Every data file (pickles, reads, PDFs of the battery rounds) is on netfiles.

## Data

`\\netfiles03.uvm.edu\bigdata_jbarry\Jarvis Data (Non VACC)\Beyond Lock Steps\` holds 14.6 GB in 6,204 files:
`DS_PTEN_figures_2026-11-16` (the battery and its frozen data), `claude_scratch_PTEN_2026-11-11_to_11-25` (the session
folder the menu and deep-round scripts ran in), `er2_store` (ML bundles and runs r001 to r017), `DS3_figures_2026-11-13`,
and `MANIFEST.csv` (every file and its size). 49 files are over 100 MB, which GitHub refuses; that is why the data is not in
git.

- From home, netfiles needs the UVM VPN. Copy what you need to a local folder (`robocopy <share folder> <local folder> /E`)
  and work on the copy.
- **Writing:** the user allowed this one folder on netfiles for analysis files. The rest of the share is the lab's primary
  data: never write anywhere else on it, and never change the PTEN mirror (put new results in a new folder).
- The original files are still on the work PC (paths in OUTPUTS_INDEX.md). The session scratch folder there is temporary.

## Setup on another machine

- This repo (Jarvis). Steps 1, 2 and 5 need Jarvis running (`http://127.0.0.1:8733`) with the user's accounts, so the
  Root Canal, X-ray and Extraction Room artifacts and the Event Bank sync in. Raw reads also need the recordings (netfiles
  or the VACC). Steps 3, 4, 6 and 7 run from the netfiles files with Python alone.
- Python with numpy, scipy, pandas, matplotlib, openpyxl, scikit-learn (the one Jarvis runs with); a second Python
  (miniconda on the work PC) with PyMuPDF for merging PDFs and python-pptx for the poster.
- The scripts carry the work PC's absolute paths; PATHS.md lists each one and where it is used.
- ML runs go to the VACC as CPU jobs through Jarvis's VACC account settings.

## Rules the user set (keep them in every output)

Words
- In the app, "P-spike"; in figures and documents, IED. The user banned one old name for the in-between class (a letter
  in front of "-spike"; see background/decisions/never-say-a-spike.md): never write it anywhere.
- The in-between class is "borderline transients (BTs)" in figures and "Twilight Zone" in the app; never "pDS".
- The two event sets are "Halo" (main) and "Strict" (check).
- American spelling. Never truncate text and never use ellipses: shrink or reflow instead.
- Plain words; explain every term on the page. Don't make up terms ("families", "hybrids", "leads").

Statistics
- Exploratory: one number per mouse; the smallest P of the applicable tests; effect sizes; no correction, no q values, no
  "survives correction" or "only a lead" language. State real confounds (recording year, probe placement, sex) as facts.
- Don't claim a cause that was not tested.
- m6 is excluded from everything. m51 (5 events) is out of statistics.
- Never call a recording "separable" on a page: show the separation index; the user makes that call.

Figures (from the story menus)
- Panel headings state the finding as a sentence.
- Significance as brackets and stars (* < 0.05, ** < 0.01, *** < 0.001) that never touch a line; on line plots, a bar along
  the axis.
- Correlation scatters with the fitted line and its 95% band; every mouse on the scale (log axis for skewed numbers).
- CSDs compared across groups share one scale (every mouse divided by the control average's deepest sink).
- Depth on the vertical axis, running down as on the probe. No lab layer labels: depth comes from each recording's own DS.
- No widows (a lone word on a line).
- 20 um per contact on the H3.

Working
- The repo is public: no secrets, emails or Drive ids in anything committed.
- Don't commit unless the user asks. Never `git restore` and never stash: another session may have work in the tree.
- Never write JavaScript or Python with backslashes through a shell heredoc; use the file-writing tool.
- Run Jarvis harnesses through PowerShell.
- Say whether Jarvis needs a restart after any change.
- No subagents unless the user asks.
- Ask before anything that writes to shared lab data (bank versions, curation sets, pools, workflows) unless it is a step
  the user already asked for.

## First tasks for the home session

1. Copy the netfiles folder locally and run the "A" checks in VERIFY_PTEN.md (battery and menus from the frozen files).
   Report what matches and what does not.
2. Ask the user the questions under "Ask the user first" in KCNT1_PLAN.md.
3. Then run KCNT1_PLAN.md step by step, checking in with the user between steps, as the PTEN work did.

## What cannot be reproduced exactly
- The depth band of each Extraction Room card and the separable calls were set by the user by hand. They are stored as
  shared prefs keyed `dentate_spike|<folder>|<gid>` and sync, so a rebuild can reuse them.
- ML runs depend on random seeds; counts at the bar move a little between runs.
- `code/pipeline_scratch/fix*.py` and `p_*.py` were one-off edits and figure fixes during the 11-16 to 11-18 rounds; they
  patched other scripts in place and are kept for the record, not to be rerun.
