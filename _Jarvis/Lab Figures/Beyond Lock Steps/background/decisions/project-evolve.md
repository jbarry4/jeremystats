# project-evolve

_PROJECT EVOLVE (2026-11-18): Rain's Planning Doc → Jarvis plan; 50 answers; built phase by phase (outline → feedback → build → user checks in Jarvis → cross off). DS work first, Kilosort last._

Source: Google Doc "Planning Doc" (Drive id on the work PC) (readable by rclone token: export + Drive comments API). Sheet "PTEN/KCNT1 Dentate Spike Data" (Drive id on the work PC). Full plan + decision table: `~/.claude/plans/project-evolve-https-docs-google-com-doc-abstract-stonebraker.md`.

**Working rule (2026-11-19):** one phase at a time. I outline the phase's plan → user gives feedback → I build → user checks it in Jarvis → refine as often as needed → cross it off → next phase. Never start the next phase unasked. DS stuff first; Kilosort ("Cells") moved to the end.

Key decisions: Root Canal save = one label → plain entry, 2+ → labeled bundle (DS / P-spike / Twilight Zone / Outside both, Halo tag kept); re-run all sets as bundles; manual branch in Event Bank; family tree in bank + every version picker; %KO in mouse records (recorded side); X-ray on P-spike/Twilight Zone with a warning; Normalize = Extraction Room sub-tab (battery landmarks); spectral/CFC/avg waveform/layer CSD = banner list + battery notes only; Purple Rain parked; DKO later; m51 descriptive only; no UI overhaul pass — new work must match existing toolkits. Cell sorts: D:\PTEN …\binary\kilosort_tl6_tu7_fs30000.0 (+invert_True twin), Isabella's curated `timestamps\<id>.mat`; binaries are on concatenated time.

**Phase 1 (bank by label), built 2026-11-19, waiting for the user's check in Jarvis.** Answers given:
- Verified runs offer Inside + Outside the border as labels.
- The workflow kind keeps the name "Ambiguous". Only the purple class is called Twilight Zone.
- Twilight Zone banked alone is type "other" with type_name "Twilight Zone".

What was built:
- New EVENT_TYPE `rcbundle` ("Root Canal bundle"). Its events carry `rc_class`, and `halo: true` when the Halo captured them.
- Label map: `rcworkflow.BANK_LABELS`.
- A bundle never overwrites a DS or P-spike entry. The run route continues the last entry of the same type.

**2026-11-21: user said do Phases 2, 3 and 7 together; SKIP 4, 5, 6.** Phase 7 answers:
- Cells = Isabella's curated cells only (timestamps folders: 32 of 39 plain runs on D:\PTEN, about 570 cells). Uncurated recordings show "sorted, not curated", never banked.
- Truth source = "novel, sophisticated management" → curation versions + diff: each source (Isabella's export, Phy's cluster_group.tsv, later re-curation) is a version of the recording's cell set in a version tree; cells matched across versions by shared spikes; diff says kept/added/removed/merged/split; user picks the version to bank, bank remembers it.
- Full Xplorefinder add-on (raster + aid-window cards, keys step cells).
- Firing around Spikes: yes, display only (raster + PETH per bundle label), no test.

**Built 2026-11-21 (phases 2, 3, 7), waiting for the user's check:**
- Phase 2: `backend/family.py` + `evolveroutes.py` (`/api/family?entry=|artifact=`, `/api/bank/<id>/branch`); bank entries carry top-level `parent`; `ui.familyTree/familyBlock`, `versionPop({family})`; Event Bank "Branch out labels…" (bundles + Cell entries).
- Phase 3 data: fresh re-runs reproduced every class exactly, so the saved runs were banked as bundles: DS 5% `2d2dcc5d66b2`, DS 10% `3a2a58a49d65`, Halo `a9cf6f2c30c2`, Strict `5469cb7ad2ae`, P-spike `204dc5977f79`. New X-ray folders Halo `xm-b2d963ef1c`, Strict `xm-7d6c8cfb0b` (calls carried) → room **v11 = v9**, **v12 = v10** recording for recording; old folders/sets archived. TZ folder `xm-4a4025594c`, P-spike folder `xm-757d1eec6c` (read, 4 + 3 X-rayed, rest under 20 events). Folder source can carry `labels`, `entry_id`; `carry_from` copies boxes/params/band/sep/flip/split/mode.
- Phase 7: `backend/cells.py`, `cellroutes.py` (`/api/cells/*`), artifact kind `cell_curation`, bank type `cell` (one row per cell, first→last spike; spikes never banked: 4 MB row cap). Kilosort tool opens on a Cells pane; add-on `web/js/cells.js` (mode `cells`, cards window `/?role=cells#cells`). 519 exported cells on 32 D:\PTEN recordings all equal the plain run's clusters (`tools/test_cells.py`); binary is InputInverted (spikes swing UP in CSC_Raw.dat).

Related: [never-say-a-spike](never-say-a-spike.md), [rootcanal-workflow-decisions](rootcanal-workflow-decisions.md), [halo-biteline-impression-decisions](halo-biteline-impression-decisions.md), [ds-pten-deep-round-1116](ds-pten-deep-round-1116.md).
