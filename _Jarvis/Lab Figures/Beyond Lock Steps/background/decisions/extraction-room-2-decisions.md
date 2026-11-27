# extraction-room-2-decisions

_2026-11-18: Extraction Room 2.0 = ML models over frozen DS sets (tab 'Room 2.0 · models'); the user's 20 answers; where the code and data live._

Asked 2026-11-18. Built in Jarvis as an Extraction Room sub-tab (`web/js/extraction_er2.js`), backend `backend/er2/` (amber, engine, nets, explain), `backend/er2run.py`, `backend/er2routes.py`, tool "er2" in `vacc_run.py`. Bundles + runs in `%LOCALAPPDATA%\Jarvis\er2` (not git). Built from the battery folder (Desktop `DS_PTEN_figures_2026-11-16\battery`).

The user's answers:
- **Targets:** all of them, each its own model: PTEN vs control, knockout %, low vs high knockout, control / IED− / IED+, and IED+ vs IED−.
- **Gestalt:** train on events, one call per mouse (pooling: event distributions, deep sets, attention). Never a call per event.
- **Inputs:**
  - Halo set, filter variants, before/after windows;
  - per-event context (intervals before and after, time in the recording, detector peak);
  - per-recording placement as nuisance covariates;
  - any per-recording data.
- **Freeze:** the winner's DS1/DS2/DS3 calls, fixed ("set in amber").
- **Placement:** "anything goes" for model inputs. I added a nuisance-only baseline row anyway.
- **Testing:** leave out one control and one PTEN mouse for PTEN vs control; leave one mouse out for everything else.
- **Bar:** AUC 0.80 / 80% right; a rank correlation of 0.70 for knockout %.
- **Many models:** the user thinks testing on mice the model never saw fixes the best-of-many problem. I disagree (picking the best still capitalizes on chance), so I show an optional shuffled-label check, which never gates a model.
- **Explaining a model:** all four methods (permutation, Shapley, drop one family, attention), consolidated into a MOST IMPORTANT list.
- **Page:** leaderboard, per-mouse calls, a feature board, and run controls.
- **VACC:** CPU jobs (the networks are numpy). Jarvis preps the data; the amber bundle travels with each run.
- **Runs:** versioned and frozen; leaderboard synced (artifact `er2_leaderboard`).

First numbers (r001 smoke test): the nuisance-only baseline alone gets AUC 0.70–0.76 for PTEN vs control (year, placement). Attention on core measures: knockout % rank correlation 0.69. The VACC env got scikit-learn installed 2026-11-18 (it lacked it).

Related: [ds-pten-m6-excluded-and-figure-rules](ds-pten-m6-excluded-and-figure-rules.md), [extraction-room-decisions](extraction-room-decisions.md), [ds-pten-deep-round-1116](ds-pten-deep-round-1116.md).
