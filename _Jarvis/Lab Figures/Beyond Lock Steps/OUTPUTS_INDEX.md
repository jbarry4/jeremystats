# Where every PTEN output is

The finished PTEN outputs were left where they were made (the user's choice, 2026-11-27). This is the map.

## In this repo (`_Jarvis/Lab Figures`, tracked in git)

| folder | date | what |
|---|---|---|
| `Archive/2026-11-16_deep_round_figures` | 11-16 | first deep round on the Halo set: DS atlas, DS1 / DS2 / DS3 classification, PTEN against control |
| `Archive/2026-11-18_room2_ML_r005` | 11-18 | Extraction Room 2.0 machine learning, run r005 (15 mice) |
| `Archive/2026-11-19_battery_run4_round11` | 11-19 | battery run 4, round 11 quality checks, the duplicate-stamp check |
| `Archive/2026-11-20_DS_PTEN_112026` | 11-20 | battery run 5 (Halo = room v9, Strict = room v10) and ML run r006 |
| `Archive/2026-11-23_DS_PTEN_112326` | 11-23 | the same plus ML runs r006 to r017 (`ml_runs/`, `ML_summary.txt`) and the summary deck `Dentate_spikes_what_we_found.html` |
| `DS_Story_Menu_112326` | 11-23 | the DS story menu (11 pages, tables, code) |
| `Jeremy_Menu_112426` | 11-24, supplements 11-25 | Jeremy's 8 questions (14 pages, tables, code) |
| `Jeremy_Menu_Followup_112526` | 11-25 | follow-up report (6 pages): held-out calls, counts per mouse, windows, layers, classes |
| `Layer_Check_112526` | 11-25 | old against tight layers (11 pages, tables, code) |
| `PTEN POSTER` | 11-25 | the poster, v1 to v3 (`PTEN poster -- UVM template v3.pptx` is the latest) |

`Archive/README.txt` explains the archive and the 20 um correction.

## On the netfiles share (not in git)

`\\netfiles03.uvm.edu\bigdata_jbarry\Jarvis Data (Non VACC)\Beyond Lock Steps\` (copied 2026-11-27; the originals on the
work PC were left in place):

| folder | size | what | original place on the work PC |
|---|---|---|---|
| `DS_PTEN_figures_2026-11-16` | 10.1 GB, 848 files | the battery (code, frozen data `battery/data`, results, merged tables, quality-check sources) and every round's figures and archives | `Desktop\DS_PTEN_figures_2026-11-16` |
| `claude_scratch_PTEN_2026-11-11_to_11-25` | 4.4 GB, 634 files | the Claude session folder: deep-round pickles (`deep_*_v10.pkl`), filter reads (`bandread9`), before / after reads (`around9`), the menus' inputs and reads (`menu/`), the poster build (`poster/`) | the session's Temp scratch folder (temporary; it may be cleared) |
| `er2_store` | 0.2 GB, 4,719 files | ML amber bundles v1 to v6 and runs r001 to r017 (leaderboards, per-task results) | `%LOCALAPPDATA%\Jarvis\er2` |
| `DS3_figures_2026-11-13` | small | the DS3 round of 11-13 | `Desktop\DS3_figures_2026-11-13` |

`MANIFEST.csv` in that folder lists every file with its size (6,204 files, 14.6 GB). 49 files are over 100 MB (the largest
301 MB), which is why none of this can go to GitHub.

## Inside Jarvis (artifacts and the Event Bank; synced through the app)

| kind | ids |
|---|---|
| pools | `07cdcb084c86` (control), `3561fc988afd` (all 18), `105b40acbbb0` (PTEN) |
| border workflows | `178daabb125c` (DS 5%), `4a29af93e601` (DS 10%), `4e5ce690d4b1` (P-spike / IED) |
| set workflows | `6fa7fef7b7a3` (Halo), `a7eee6a6ca9f` (Strict) |
| Meta Workflow instances | `21486d872fcf` (5%), `d354491b0eee` (10%) |
| Root Canal bundles | Halo `a9cf6f2c30c2`, Strict `5469cb7ad2ae`, DS 5% `2d2dcc5d66b2`, DS 10% `3a2a58a49d65`, P-spike `204dc5977f79` |
| X-ray Many folders | Halo `xm-b2d963ef1c`, Strict `xm-7d6c8cfb0b`, Twilight Zone `xm-4a4025594c`, P-spike `xm-757d1eec6c` |
| Extraction Room | room `dentate_spike`, artifact `980b57eab496`: Halo v9 / v11, Strict v10 / v12 |
| hand-sorted IED sets in the bank | m13 `964aac87949e`, m28 `15de830c8b35`, m3 `754a4ab49e03`, m5 `51c1d1150100`, m34 `2bcb129a3db5` |
| recordings (registry gids) | in `code/menus/m0_data.py` (`GIDS`) |

Root Canal reads and X-ray reads are machine-local caches. The running app copies them to the VACC shelf
(`/gpfs2/scratch/sakhava1/Jarvis Data/_answers`), so another machine can fetch them without reading the raw files again.
