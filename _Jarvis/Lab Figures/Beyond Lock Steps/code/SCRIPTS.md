# Every copied script, with the first paragraph of its own docstring

Generated 2026-11-27 by the packing script. Folders: battery (the frozen test battery, from the Desktop folder
DS_PTEN_figures_2026-11-16/battery), pipeline_scratch (the session's analysis scripts: deep round, reads, dedupe, room
rebuilds, battery runs, ML driver), menus (story menu, Jeremy menu, follow-up, supplements, layer check), poster.

## battery

| file | what it says it does |
|---|---|
| analyze.py | Merges every family's results and makes the corrections. |
| around_measures.py | THE BEFORE/AFTER BATTERY (asked 2026-11-18: "the activity a bit after and before the DS ... sometimes there's a bit of oscillations or some activity before and after"). |
| build_dataset.py | Freezes one event set (v6 = Halo set, v8 = No P-spikes set) of the Extraction Room into a single file the battery reads: data/ds_<set>.pkl. Run once by the main session; nothing here talks to Jarvis. |
| derive_v8.py | The No P-spikes set (v8) made from the Halo set (v6), 2026-11-19. |
| dsdata.py | The frozen dentate-spike pilot dataset (2026-11-16) and the depth normalization. READ ONLY: nothing here writes, and nothing here talks to Jarvis. See README.md for every field. |
| harness.py | Every measure of the pilot battery goes through the same contrasts. |
| house.py | The look of every PDF in this folder (the lab's Nature-style figures): fonts, colors, millimeter placement. No data, no Jarvis. |
| leads_run5_patch.py | Lead words updated to battery run 5 (2026-11-19: room v9, duplicate stamps removed, m1 on Lock's stamps). Only leads whose numbers moved are touched; run 4's lists are in archive_run4_2026-11-19/battery/code/. python leads_run5_patch.py |
| make_averaged.py | The averaged documents: the dentate spike normalized across recordings. round10/Averaged_CTL.pdf control round10/Averaged_PTEN.pdf PTEN: all, IED-, IED+ round10/Averaged_comparison.pdf groups laid over each other, with a cluster permutation test of each curve python make_averaged.py |
| make_averaged2.py | The one normalized figure (2026-11-17, replacing round 10's four averaged pages): DS1 and DS2, the DS3 events taken out, depth normalized, averaged over recordings. round11/Averaged_DS1_DS2.pdf page 1 control, page 2 PTEN (all), page 3 PTEN IED-, page 4 PTEN IED+, page 5 the groups laid over each other (cluster permutation test, raw P). No folded axes, no "separable" labels: every recording is drawn on its own beside the mean, with its separation index, so the reader decides. python make_averaged2.py |
| make_leads.py | Each lead from the UNCORRECTED battery, explained from the waveform up (asked 2026-11-17: "figures leading up to the figure ... where on the waveform that is true ... I am not sure what the Y axis is"). battery_reports/uncorrected/Leads_explained_UNCORRECTED.pdf One page a lead: a where on the dentate spike the number is read (mean CSD, example recording) b one event, step by step c every event of two example recordings (one per side of the contrast) d every event of every recording, with the per-recording number marked e the result: one number per recording, by group and against knockout then the numbers, what speaks against it, and what would test it. The list and the words are in leads.json. python make_leads.py |
| make_reports.py | The battery's two reports and their tables. battery_reports/uncorrected/Battery_UNCORRECTED.pdf, all_tests_UNCORRECTED.csv battery_reports/corrected/Battery_corrected.pdf, all_tests_corrected.csv battery_reports/measures.csv (every measure: what it is and its 16 numbers) python make_reports.py |
| make_room2.py | Extraction Room 2.0, preliminary write-up (2026-11-18): methods and results PDFs from the VACC run r006 (2026-11-20, amber v3: the Halo set with m21 in; r005 left m21 out, r003 and r004 were run 4 data). |
| make_room2_figs.py | Extraction Room 2.0 -- the journal figures (2026-11-18). |
| make_sanity.py | SANITY CHECK of the DS1 / DS2 names and of DS3, one document per group: round11/Sanity_check_CTL.pdf, round11/Sanity_check_PTEN.pdf Asked 2026-11-17: why do m2, m60, m13, m3, m5 and m34 have more DS1 than DS2, and is DS3 doing what it is supposed to? For every recording, under the classifier the other pages use (the best eligible one by separation index): a each type's mean CSD down the probe, past the analyzed band, with the two contacts DS3 is scored on b how many events are DS1, DS2, DS3 (the classifier alone; DS3 as Jarvis scored it; DS3 scored again with the layers looked for past the band) c every event's sink at the outer contact against its sink at the middle contact: the DS3 rule is the green wedge, the noise floor the gray corner d the DS3 score of every event, DS1 and DS2 stacked python make_sanity.py |
| make_supplement.py | Supplemental figures (round11/Supplemental_figures.pdf): how the classification choices behave. python make_supplement.py |
| make_table.py | The summary table: one row per recording, every classifier's separation index as a colored cell, and the averages. round11/Summary_table.pdf / .png / .csv |
| make_top10.py | The ten most interesting leads from the UNCORRECTED battery, one page each: battery_reports/uncorrected/Top10_leads_UNCORRECTED.pdf The list and the words are in top10.json (chosen by hand from the uncorrected table: effect size, the other event set, other classifiers, confounds and biology, not only the smallest P). python make_top10.py |
| measures.py | The battery's measures: four families (timing, waveform, laminar, structure), every one pushed through harness.Battery so it gets the same contrasts. One number per recording per measure. |
| normcurves.py | The dentate spike of each recording on axes that are the same in every mouse, and the literature's way of finding DS3. Used by the averaged documents, the quality check pages, the summary table and the battery. |
| room2_r005_patch.py | Point the Room 2 write-up and figures at run r005 (2026-11-19: amber v2, duplicate stamps removed, m1 on Lock, m21 without a winner so 15 mice). python room2_r005_patch.py |
| room2_r006_patch.py | Point the Room 2 write-up and figures at run r006 (2026-11-20: amber v3, the Halo set with m21 back in, 16 mice). Applied after room2_r005_patch.py. python room2_r006_patch.py |
| extract/around_read.py | THE BEFORE/AFTER READ (2026-11-18): every Halo-set (v6) event, and as many random moments of the same recording (at least 1 s from any event), read from the raw recording, +-500 ms around each. Read only. |
| extract/band_build.py | The filter battery's event sets: the Halo set (v6) with every event's whole-shank CSD and LFP made again from bandread/<lab>.pkl under one filter, by Jarvis's own fit (the room's box, interpolated contacts and time window), and everything else -- events, types, names, DS3 -- left as the room's. Writes battery/data/ds_b_<band>.pkl. Read only: Jarvis's split cache is pointed at a scratch folder for the run. |
| extract/band_read.py | Every Halo-set (v6) event read again from the raw recording, once, and cut out under several filters at the same time. Same events, same times (each event's refined time from the room's read), same contacts, same bad contacts repaired the same way; only the filter differs. Read only: nothing is written into Jarvis. |
| extract/deep_ds3.py | The DS3 score (Tarcsay et al. 2025 relative sink, backend/dsmix.relsink) of every event under the classifications the quality check draws that the room does not already hold: the two mixtures and the two optimized boundaries on the PCA plane. Read only. |
| extract/deep_ds3_7.py | The DS3 score (Tarcsay et al. 2025 relative sink, backend/dsmix.relsink) of every event under the classifications the quality check draws that the room does not already hold: the two mixtures and the two optimized boundaries on the PCA plane. Read only. |
| extract/deep_extra.py | The whole shank per recording (CSD and LFP, every event at the DS and the mean over time), added to deep_v*.pkl as deep_full_v*.pkl. Read only. |
| extract/deep_extra_7.py | The whole shank per recording (CSD and LFP, every event at the DS and the mean over time), added to deep_v*.pkl as deep_full_v*.pkl. Read only. |
| extract/deep_extract.py | Everything per event and per recording the room holds, for one room version (argv 1; 6 = Halo, 8 = No P-spikes), pickled. Read only. |
| extract/deep_opt.py | The other way round: a boundary on the PCA plane (PC1, PC2) chosen to make the DS1-DS2 separation index as high as it can be -- a straight line at any angle, and a curve (a parabola about that line) -- with each type holding at least 5% of events. Beside the conventional mixture boundaries (deep_pca2.py). Because the index is now both target and yardstick, each is also fitted on a random half of the events and scored on the other half (5 times). Read only. |
| extract/deep_opt2.py | A curve on the PCA plane (PC1, PC2) chosen to maximize the AVERAGE of the upper-blade and lower-blade separation index (each blade's own sink overlap), each type holding 5% of events or more. Also saves the three overlap matrices (both sinks, upper, lower) so any classification can be scored per blade. Held out: fitted on a random half, scored on the other half (5 times). Read only. |
| extract/deep_opt2_7.py | A curve on the PCA plane (PC1, PC2) chosen to maximize the AVERAGE of the upper-blade and lower-blade separation index (each blade's own sink overlap), each type holding 5% of events or more. Also saves the three overlap matrices (both sinks, upper, lower) so any classification can be scored per blade. Held out: fitted on a random half, scored on the other half (5 times). Read only. |
| extract/deep_opt_7.py | The other way round: a boundary on the PCA plane (PC1, PC2) chosen to make the DS1-DS2 separation index as high as it can be -- a straight line at any angle, and a curve (a parabola about that line) -- with each type holding at least 5% of events. Beside the conventional mixture boundaries (deep_pca2.py). Because the index is now both target and yardstick, each is also fitted on a random half of the events and scored on the other half (5 times). Read only. |
| extract/deep_pca2.py | Two more classifiers on the PCA plane (PC1, PC2), for the quality check: a two-Gaussian mixture with a shared covariance (a straight boundary at any angle) and with its own covariance per type (a curved boundary). Ten starts each; scored on the same separation index as the other fifteen; stability = the share of events that keep their type when the mixture is refitted on 40 bootstrap resamples. Read only. |
| extract/deep_pca2_7.py | Two more classifiers on the PCA plane (PC1, PC2), for the quality check: a two-Gaussian mixture with a shared covariance (a straight boundary at any angle) and with its own covariance per type (a curved boundary). Ten starts each; scored on the same separation index as the other fifteen; stability = the share of events that keep their type when the mixture is refitted on 40 bootstrap resamples. Read only. |
| extract/lfp_ref_check.py | Is the 'where the LFP is largest' result a reference effect? Same measure with the LFP as recorded and with a common-median reference (each event's median over the good contacts subtracted from every contact, which removes anything every contact shares, the reference included). |
| extract/lfp_shape_ref.py | General lead 4 (LFP above the upper blade, share of its largest value): does it hold once the part every contact shares is taken out? |
| extract/ref_headers.py | What each Halo recording's .ncs headers say about the reference. Read only. |
| extract/run_v7.sh | (no docstring; read the file) |
| qc_source/deep_ds3.py | The DS3 score (Tarcsay et al. 2025 relative sink, backend/dsmix.relsink) of every event under the classifications the quality check draws that the room does not already hold: the two mixtures and the two optimized boundaries on the PCA plane. Read only. |
| qc_source/deep_extra.py | The whole shank per recording (CSD and LFP, every event at the DS and the mean over time), added to deep_v*.pkl as deep_full_v*.pkl. Read only. |
| qc_source/deep_extract.py | Everything per event and per recording the room holds, for one room version (argv 1; 6 = Halo, 8 = No P-spikes), pickled. Read only. |
| qc_source/deep_figs.py | Three figures in the house Nature style (PDF vector + PNG 300 dpi): 1 the atlas, 2 the two families and the hybrids, 3 PTEN against control. |
| qc_source/deep_opt.py | The other way round: a boundary on the PCA plane (PC1, PC2) chosen to make the DS1-DS2 separation index as high as it can be -- a straight line at any angle, and a curve (a parabola about that line) -- with each type holding at least 5% of events. Beside the conventional mixture boundaries (deep_pca2.py). Because the index is now both target and yardstick, each is also fitted on a random half of the events and scored on the other half (5 times). Read only. |
| qc_source/deep_opt2.py | A curve on the PCA plane (PC1, PC2) chosen to maximize the AVERAGE of the upper-blade and lower-blade separation index (each blade's own sink overlap), each type holding 5% of events or more. Also saves the three overlap matrices (both sinks, upper, lower) so any classification can be scored per blade. Held out: fitted on a random half, scored on the other half (5 times). Read only. |
| qc_source/deep_pca2.py | Two more classifiers on the PCA plane (PC1, PC2), for the quality check: a two-Gaussian mixture with a shared covariance (a straight boundary at any angle) and with its own covariance per type (a curved boundary). Ten starts each; scored on the same separation index as the other fifteen; stability = the share of events that keep their type when the mixture is refitted on 40 bootstrap resamples. Read only. |
| qc_source/deep_qc11.py | Quality check, round 5: one page a recording, laid out as three rows that read the same way -- the classifier used, the conventional boundary on the PCA plane, and the boundary optimized for the separation index -- each with the PCA plane, every event, the DS1 and DS2 means and the sink amplitudes, in the same columns. |
| qc_source/deep_qc5.py | Quality check, round 5: one page a recording, laid out as three rows that read the same way -- the classifier used, the conventional boundary on the PCA plane, and the boundary optimized for the separation index -- each with the PCA plane, every event, the DS1 and DS2 means and the sink amplitudes, in the same columns. |
| qc_source/deep_stats.py | One number a recording for every measure; PTEN against CTL, the knockout dose, the ordered trend; BH over the lot; the same on the No P-spikes set. |
| qc_source/deep_stats2.py | The leads from deep_stats.py, pressed: the granule-layer source against the blade sinks measured six ways on the whole shank; the best split per animal on the shared yardstick (SI); the vote across methods; and what the whole 153-test family gives by chance (max-statistic permutation). |

## pipeline_scratch

| file | what it says it does |
|---|---|
| around_read.py | THE BEFORE/AFTER READ (2026-11-18): every Halo-set (v6) event, and as many random moments of the same recording (at least 1 s from any event), read from the raw recording, +-500 ms around each. Read only. |
| aud0.py | Audit probe: what bank entries does one recording have, and their versions. Read only. |
| aud1.py | Audit step 1: the workflows behind the battery sets, their pools, and one member's full record. Read only. |
| aud2.py | Audit step 2: does every event the battery used come from the newest Lock (Confluence) version of its recording? Event by event. Read only. |
| aud3.py | Audit step 3: battery times against the pool and the bank with a tolerance, duplicates, and m1's undone alignment. Read only. |
| aud4.py | Audit step 4: pairs of good stamps under 1 ms apart in the pooled entries. Read only. |
| band_build.py | The filter battery's event sets: the Halo set (v6) with every event's whole-shank CSD and LFP made again from bandread/<lab>.pkl under one filter, by Jarvis's own fit (the room's box, interpolated contacts and time window), and everything else -- events, types, names, DS3 -- left as the room's. Writes battery/data/ds_b_<band>.pkl. Read only: Jarvis's split cache is pointed at a scratch folder for the run. |
| band_check.py | Where would 'the edges of the two bottom sinks' put the band, against the box the user drew in X-ray for the same read? |
| band_diff.py | (no docstring; read the file) |
| band_read.py | Every Halo-set (v6) event read again from the raw recording, once, and cut out under several filters at the same time. Same events, same times (each event's refined time from the room's read), same contacts, same bad contacts repaired the same way; only the filter differs. Read only: nothing is written into Jarvis. |
| band_shortlist.py | Filter-battery candidates: a group difference that shows under another filter, is weaker under the DS filter (5-100 Hz), and shows (same sign, P < 0.10) under a related filter too. python band_shortlist.py [n] |
| blob_real.py | Blob Analysis on the real new-round set (room v3, CTL Baseline Snap 10%), without saving an Impression: every card as it stands, calls taken as separable for the test only. |
| calls_check.py | The calls made on each new-round set, beside the Bite line's split and SI before (bumps: v3/v4) and now (humps: v5/v6). |
| camel_bad.py | Why each contact is marked bad on each recording of the room's v4, and the probe/spacing it was read with. |
| camel_cubic.py | Where the camel dips sit with the bad contacts repaired linearly (as read) and cubically: do the dips at repaired contacts go away? |
| camel_diag.py | The camel hump: is a contact bad, drifting, or is the dip real? |
| camel_gain.py | Is a contact's gain off? Each contact predicted from two neighbours on each side (4-point cubic: exact for any field smooth to third order, so a real sink does not look like a gain error the way it does against 2 neighbours), the slope of the measured on the predicted in the baseline (/t/ > 30 ms), and the gain change at the camel's dip that would remove the dip. Usage: camel_gain.py <label> [dip contact] [version] |
| camel_m6.py | m6 s4's top hump: two sub-sinks (about 35 and 40) with a dip at 38. Per event: both sub-sinks' strength, the dip, and how the share between them is distributed -- one population with a camel in every event (a fixed artefact or two layers always active together), or two populations (each event mostly one sub-sink: the DS1/DS2 difference itself). |
| camel_merge.py | Does the Bite line follow the camel's bookkeeping? And does merging a camel into one bump fix it? |
| camel_probe.py | What a read holds, for m6 s4 in the room's v3/v4. |
| camel_saved.py | What the user has saved in the room for the new-round sets: splits and bands, by set and recording. |
| camel_show.py | Print one recording's per-contact numbers from camel_diag.json. |
| camel_try.py | Three remedies for the camel hump, on every recording of a room version: |
| ctx_extract.py | Extract text (and render a few key pages) from the context documents. |
| dedupe.py | Duplicate Spike stamps (user, 2026-11-19): neighbours under 10 ms apart are one event. In each run of them, the stamp with the largest CSD sink stays a Spike; the others become Garbage, in a new version of the Confluence set. Nothing moves or is deleted. Dry run unless --apply. |
| deep_ds3.py | The DS3 score (Tarcsay et al. 2025 relative sink, backend/dsmix.relsink) of every event under the classifications the quality check draws that the room does not already hold: the two mixtures and the two optimized boundaries on the PCA plane. Read only. |
| deep_ds3_10.py | The DS3 score (Tarcsay et al. 2025 relative sink, backend/dsmix.relsink) of every event under the classifications the quality check draws that the room does not already hold: the two mixtures and the two optimized boundaries on the PCA plane. Read only. |
| deep_ds3_7.py | The DS3 score (Tarcsay et al. 2025 relative sink, backend/dsmix.relsink) of every event under the classifications the quality check draws that the room does not already hold: the two mixtures and the two optimized boundaries on the PCA plane. Read only. |
| deep_extra.py | The whole shank per recording (CSD and LFP, every event at the DS and the mean over time), added to deep_v*.pkl as deep_full_v*.pkl. Read only. |
| deep_extra_10.py | The whole shank per recording (CSD and LFP, every event at the DS and the mean over time), added to deep_v*.pkl as deep_full_v*.pkl. Read only. |
| deep_extra_7.py | The whole shank per recording (CSD and LFP, every event at the DS and the mean over time), added to deep_v*.pkl as deep_full_v*.pkl. Read only. |
| deep_extract.py | Everything per event and per recording the room holds, for one room version (argv 1; 6 = Halo, 8 = No P-spikes), pickled. Read only. |
| deep_figs.py | Three figures in the house Nature style (PDF vector + PNG 300 dpi): 1 the atlas, 2 the two families and the hybrids, 3 PTEN against control. |
| deep_final.py | The numbers the figures draw: sixteen measures chosen for what they mean (not for their p), effect sizes with bootstrap intervals, one global test (can a recording's group be told from its dentate spikes, leaving that animal out), the chance level of the whole search, and what n a real test of the best lead would need. |
| deep_look.py | A quick look: every recording's mean DS down the whole shank. |
| deep_opt.py | The other way round: a boundary on the PCA plane (PC1, PC2) chosen to make the DS1-DS2 separation index as high as it can be -- a straight line at any angle, and a curve (a parabola about that line) -- with each type holding at least 5% of events. Beside the conventional mixture boundaries (deep_pca2.py). Because the index is now both target and yardstick, each is also fitted on a random half of the events and scored on the other half (5 times). Read only. |
| deep_opt2.py | A curve on the PCA plane (PC1, PC2) chosen to maximize the AVERAGE of the upper-blade and lower-blade separation index (each blade's own sink overlap), each type holding 5% of events or more. Also saves the three overlap matrices (both sinks, upper, lower) so any classification can be scored per blade. Held out: fitted on a random half, scored on the other half (5 times). Read only. |
| deep_opt2_10.py | A curve on the PCA plane (PC1, PC2) chosen to maximize the AVERAGE of the upper-blade and lower-blade separation index (each blade's own sink overlap), each type holding 5% of events or more. Also saves the three overlap matrices (both sinks, upper, lower) so any classification can be scored per blade. Held out: fitted on a random half, scored on the other half (5 times). Read only. |
| deep_opt2_7.py | A curve on the PCA plane (PC1, PC2) chosen to maximize the AVERAGE of the upper-blade and lower-blade separation index (each blade's own sink overlap), each type holding 5% of events or more. Also saves the three overlap matrices (both sinks, upper, lower) so any classification can be scored per blade. Held out: fitted on a random half, scored on the other half (5 times). Read only. |
| deep_opt_10.py | The other way round: a boundary on the PCA plane (PC1, PC2) chosen to make the DS1-DS2 separation index as high as it can be -- a straight line at any angle, and a curve (a parabola about that line) -- with each type holding at least 5% of events. Beside the conventional mixture boundaries (deep_pca2.py). Because the index is now both target and yardstick, each is also fitted on a random half of the events and scored on the other half (5 times). Read only. |
| deep_opt_7.py | The other way round: a boundary on the PCA plane (PC1, PC2) chosen to make the DS1-DS2 separation index as high as it can be -- a straight line at any angle, and a curve (a parabola about that line) -- with each type holding at least 5% of events. Beside the conventional mixture boundaries (deep_pca2.py). Because the index is now both target and yardstick, each is also fitted on a random half of the events and scored on the other half (5 times). Read only. |
| deep_pca2.py | Two more classifiers on the PCA plane (PC1, PC2), for the quality check: a two-Gaussian mixture with a shared covariance (a straight boundary at any angle) and with its own covariance per type (a curved boundary). Ten starts each; scored on the same separation index as the other fifteen; stability = the share of events that keep their type when the mixture is refitted on 40 bootstrap resamples. Read only. |
| deep_pca2_10.py | Two more classifiers on the PCA plane (PC1, PC2), for the quality check: a two-Gaussian mixture with a shared covariance (a straight boundary at any angle) and with its own covariance per type (a curved boundary). Ten starts each; scored on the same separation index as the other fifteen; stability = the share of events that keep their type when the mixture is refitted on 40 bootstrap resamples. Read only. |
| deep_pca2_7.py | Two more classifiers on the PCA plane (PC1, PC2), for the quality check: a two-Gaussian mixture with a shared covariance (a straight boundary at any angle) and with its own covariance per type (a curved boundary). Ten starts each; scored on the same separation index as the other fifteen; stability = the share of events that keep their type when the mixture is refitted on 40 bootstrap resamples. Read only. |
| deep_probe.py | What the room holds per recording and per event (read only). |
| deep_qc.py | Quality check: the DS1/DS2 classification of every recording, one page each (a PNG per recording and one PDF with a page per recording). |
| deep_qc11.py | Quality check, round 5: one page a recording, laid out as three rows that read the same way -- the classifier used, the conventional boundary on the PCA plane, and the boundary optimized for the separation index -- each with the PCA plane, every event, the DS1 and DS2 means and the sink amplitudes, in the same columns. |
| deep_qc5.py | Quality check, round 5: one page a recording, laid out as three rows that read the same way -- the classifier used, the conventional boundary on the PCA plane, and the boundary optimized for the separation index -- each with the PCA plane, every event, the DS1 and DS2 means and the sink amplitudes, in the same columns. |
| deep_stats.py | One number a recording for every measure; PTEN against CTL, the knockout dose, the ordered trend; BH over the lot; the same on the No P-spikes set. |
| deep_stats2.py | The leads from deep_stats.py, pressed: the granule-layer source against the blade sinks measured six ways on the whole shank; the best split per animal on the shared yardstick (SI); the vote across methods; and what the whole 153-test family gives by chance (max-statistic permutation). |
| deep_unc.py | The raw tests, no correction: the 15 chosen measures and all 240. |
| deep_words.py | The captions and the per-mouse table that go with the three figures. |
| ds3_battery.py | A wide battery on the Halo set (room v6) as it stands: every per-recording measure, PTEN against CTL, the knockout dose among PTEN, the ordered trend CTL < low KO < high KO -- all corrected together (BH) -- and the checks against the literature. One number a recording; nothing saved. |
| ds3_fig.py | The DS3 round's figure (Halo set, room v6, Impression v2), in the house Nature style: PDF (vector) and PNG (300 dpi), and the robustness numbers. |
| ds3_round.py | The user's ask (2026-11-13) on the Halo set (room v6): every recording on the Bite line at the lowest point of its cost curve, DS3 on, an Impression of that state, and a fresh round of stats on DS3 -- PTEN against CTL. |
| dups_fig.py | Every pair of Spike stamps under 1 ms apart in the 18 Confluence sets, drawn from the pools' own Root Canal reads, for a by-eye check. Read only. |
| engine_old.py | Targets, input views, models and mouse-level testing for Extraction Room 2.0. |
| er2_follow.py | Follow one ER2 VACC run home: python er2_follow.py r006 |
| er2_go.py | ML battery (Extraction Room 2.0) on the deduplicated data, 2026-11-19. Waits for battery run 5's merged tables, builds amber bundle v2 through the running Jarvis, submits the same run as r003 (all targets, views and models, explain + drop-one-family, no shuffles) to the VACC, and follows it home. |
| er2_types_driver.py | The DS-type ML program (2026-11-20), out of the Jarvis process (the new engine code is pushed to the VACC with each run). Makes the runs in order, submits each when the queue has room (the account takes 1000 jobs), brings answers home, resubmits failed tasks once, and writes each leaderboard. State in er2_types_state.json; safe to restart (it picks up where it was). |
| facts.py | (no docstring; read the file) |
| fix10.py | Quality check round 3: two Gaussian-mixture classifiers on the PCA plane join the fifteen; a PC1/PC2 panel with the boundaries; the sink panel says when a type's sink is under its floor; nothing overlaps. |
| fix11.py | (no docstring; read the file) |
| fix12.py | (no docstring; read the file) |
| fix13.py | Quality check round 4: the conventional boundaries (g) beside boundaries chosen to maximise the separation index (h), and how far the events move. |
| fix14.py | Round 6: the depth range is widened past the analysed band (5 contacts a side, more while a sink is still above its noise floor at the edge), so a sink at the band's edge is seen whole. The band's limits are drawn. |
| fix15.py | Round 7: the row with the highest separation index is marked; a sink under its noise floor gets a faint tick at its peak; DS1 and DS2 ticks sit side by side, never on top of each other. |
| fix16.py | Round 8: each row also gives the index in each blade; row 3 says what maximizing the mean of the two blades gives; American spelling. |
| fix17.py | Round 9: DS3 in every row. Two more panels a row -- DS3's sink with its ticks, and DS1 and DS2 again without the DS3 events -- and the green label becomes FINAL OPTIMIZED SEPARATION, given to the row whose DS1 and DS2 are best separated once DS3 is out. |
| fix18.py | Round 10 of the quality check: DS3 wording, the paper's own procedure for DS3, and a fourth row with the recording on the normalized axes. |
| fix2.py | (no docstring; read the file) |
| fix3.py | (no docstring; read the file) |
| fix4.py | (no docstring; read the file) |
| fix5.py | Standard terms only: no 'families', 'hybrids', 'splits', 'leads', 'shuffles'. |
| fix6.py | (no docstring; read the file) |
| fix7.py | Round 2 of the sink comparison: both types on one absolute scale, inside the analysed band, with s.e.m. and each type's noise floor; an offset only where DS1's sink clears its floor. |
| fix8.py | (no docstring; read the file) |
| fix9.py | (no docstring; read the file) |
| fix_m1.py | Phase 1: put Lock's alignment of PTEN m1 s2 (Confluence entry bfa98498290b) back on top. Replays the committed Lock pass br1f1b0830ec -- its own moves, by index, with its own params -- onto the live events (v3, identical to the v1 it was made from), as a new aligned version. Dry run unless --apply. |
| gain_fix.py | Do the off-gain contacts matter? Each recording refitted with them taken out (made again from two good neighbours a side, cubic), and the Bite line (humps) compared: split, SI, notched events, and the mean profile. |
| gain_scan.py | Every recording of a room version: each contact's gain against a 4-point (cubic) prediction from two neighbours a side, in the baseline (/t/ > 30 ms), by quarter of the recording (drift). Lists the contacts that stand out: more than 1.5% off and more than 5 MADs from the recording's median, or a quarter-to-quarter swing over 1.5% (drift). Writes gain_scan.json. |
| halo_apply_real.py | Apply the Halo (2x / 1.5x) to 'Ambiguous Dataset (Optimized Parameters/Snap)' v2 and bank its DS side, through the app's own routes (in-process). |
| halo_check.py | Check the Halo's gauges against the run's own classes, on a real run. |
| halo_pspike_check.py | Does the Halo set (room v9) hold any P-spike? Read only. 1. The classes of the room's events in their workflow run (Halo Ambiguous 6fa7fef7b7a3 v5). 2. The P-spike border's own run: any room event that run calls inside the P-spike border. 3. The hand-curated P-spike sets: any room event within 20 ms of a stamp labeled P-spike. |
| humps_check.py | The humps on real arrays: the Bite line's split and SI under humps vs bumps, the view's new fields, and the blobs. |
| integ1.py | Data integrity, step 1: what the two room sets are made of -- their workflows, pools, X-ray Many folders and the room versions -- read only. |
| integ2.py | Data integrity, step 2: event by event. The pools' members and their groups, the borders' definitions, every room event's class under each run, and each read's stamps against the run's kept stamps. Read only. |
| interp_m6.py | m6 s4: 38 and 39 interpolated (the user's call, 2026-11-13), through the app's own route; the card before and after; and the "no DS1" call and the length checked in memory (the call faked, nothing written). |
| layers_check.py | Which of the DS recordings carry real layer labels (not placeholders) in Jarvis's layer store? |
| lfp_ref_check.py | Is the 'where the LFP is largest' result a reference effect? Same measure with the LFP as recorded and with a common-median reference (each event's median over the good contacts subtracted from every contact, which removes anything every contact shares, the reference included). |
| lfp_shape_ref.py | General lead 4 (LFP above the upper blade, share of its largest value): does it hold once the part every contact shares is taken out? |
| list_versions.py | Read only: the dentate_spike room's versions, their sets and event counts. |
| m6_3839.py | Are contacts 38/39 on m6 s4 at fault? Five tests on its read (room v8). |
| make_112326.py | (no docstring; read the file) |
| meta_crash_test.py | Start (or resume) the 5% meta workflow through the real route, print its progress as it changes, then kill the process outright after LIMIT seconds: a crash, as far as the run can tell. |
| new_set.py | The user's ask of 2026-11-13: in the Workflow tab, "PTEN and CTL Baseline (Optimized Paramters/Snap/10% Grace[Extraction Room]))" with the latest inputs, then put it in the Extraction Room in place of the CTL Baseline 10% set. Through the app's own routes, in-process. Not banked (the room reads the run; the bank already holds these events as ad9b1441cdaa). |
| p2.py | Phase 2, through the running Jarvis (http://127.0.0.1:8733), so nothing needs a restart. Steps (argv): check / read / save / run. |
| p2_archive.py | Archive every Root Canal pool, workflow and border outside the current chain, the way the UI does (shared prefs merged per id; a workflow's bank entries archived with it). Through the running Jarvis. Dry run unless --apply. |
| p2_compare.py | Phase 2 check: each workflow's new run against its previous run, per mouse. m1's events are paired through Lock's own moves (old time -> new time). Read only. |
| p3.py | Duplicate fix, Root Canal part, through the running Jarvis. read -- read each deduped Confluence set's newest version (one job each) save -- refit + save the three pools with the new reads (--apply to save) run -- rerun the four workflows on the newest pools, unbanked |
| p3_compare.py | Dedupe check: each workflow's new run against its previous one, per mouse. Events are matched by (recording, time). Read only. |
| p3v.py | The deduped Confluence sets' reads, on the VACC, as one Root Canal batch (where: vacc, forced) through the running Jarvis. Merges into p3_reads.json. |
| p4.py | Phase 3, through the running Jarvis: the two room sets rebuilt from the fixed workflow runs. folder -- a new X-ray Many folder per set from the newest run (ids -> p4_state.json) read -- read each new folder (one job each) copy -- carry every per-set decision (band, call, split, flip, mode) from the old folder extract -- the room's next version from each new folder (direct round), then archive the old sets check -- each card's stamps against its run's kept stamps |
| p4_calls.py | What the room itself says each old set's calls are (own keys plus any older room/gid calls that belong to it), against what p4 copy would carry. Read only. |
| p_around_leads.py | (no docstring; read the file) |
| p_avg3.py | (no docstring; read the file) |
| p_band_leads.py | (no docstring; read the file) |
| p_bat.py | (no docstring; read the file) |
| p_dsdata.py | (no docstring; read the file) |
| p_figs1.py | (no docstring; read the file) |
| p_figs2.py | (no docstring; read the file) |
| p_figs3.py | (no docstring; read the file) |
| p_figs4.py | (no docstring; read the file) |
| p_figs5.py | (no docstring; read the file) |
| p_leads.py | (no docstring; read the file) |
| p_leads2.py | (no docstring; read the file) |
| p_leads3.py | (no docstring; read the file) |
| p_leads4.py | (no docstring; read the file) |
| p_leads_1118.py | (no docstring; read the file) |
| p_meas2.py | (no docstring; read the file) |
| p_qc11.py | deep_qc5.py -> deep_qc11.py: round 11 of the quality check (2026-11-17). |
| p_san2.py | (no docstring; read the file) |
| p_supp.py | (no docstring; read the file) |
| p_table.py | (no docstring; read the file) |
| p_winner.py | (no docstring; read the file) |
| pool_members.py | Which sessions of m3, m5, m13, m28, m34 the PTEN Baseline v2 pool holds. |
| pres_sum.py | (no docstring; read the file) |
| psets.py | The hand-sorted / confirmed P-spike sets the workflow builder offers: every version, what made it, aligned or not, by whom. |
| psets_braces.py | Every Eye/Braces alignment made of the P-spike sets: from which version, with what settings, reviewed or not, and each row's call. |
| pspike_wfs.py | Which hand-sorted sets each P-spike workflow is drawn around, at which version. |
| ref_headers.py | What each Halo recording's .ncs headers say about the reference. Read only. |
| room_reads.py | Make the two X-ray Many folders the new room round reads from, and read every recording of each at its kept events (in-process, through the app's own routes). Prints progress; safe to run again (reads already here are skipped, and a folder with the same source is not made twice). |
| room_refit.py | Fit the two new-round sets again, as the room's next versions, with the Bite line on the recording's two humps -- through the app's own route, in-process -- and say each card's line under it. |
| room_takein.py | Take the two new sets into the Extraction Room (fitted here, no X-ray) and archive the two old ones -- through the app's own routes, in-process. |
| run5.sh | Battery run 5 (2026-11-19): everything again on Extraction Room v9 (deduplicated Halo set). |
| run5_compare.py | Battery run 5 (deduplicated, room v9) against run 4 (archived). Read only. |
| run5b.sh | Battery run 5 (2026-11-19): everything again on Extraction Room v9 (deduplicated Halo set). |
| run5c.sh | Battery run 5 (2026-11-19): everything again on Extraction Room v9 (deduplicated Halo set). |
| sc2.py | (no docstring; read the file) |
| sc3.py | (no docstring; read the file) |
| sc4.py | (no docstring; read the file) |
| sc5.py | (no docstring; read the file) |
| sc6.py | (no docstring; read the file) |
| shortlist.py | (no docstring; read the file) |
| shortlist2.py | (no docstring; read the file) |
| shortlist4.py | Run 4 candidates: raw P < 0.05 on the Halo set, same sign and P < 0.10 on the No P-spikes set; no absolute distances or amplitudes (2026-11-18). python shortlist4.py general/typed/ds3/q [n] |
| split15.py | The fifteen splits and the low-contacts look on real cards, through the app's own routes, in-process. argv: room version, then session labels (substrings); none = every card. |
| stale_check.py | The room's v4 and v6 through the app's route: which saved Bite lines are stale under each, and the m2 s3 split view's band. |
| strict_all.sh | The Strict set end to end (2026-11-19): Extraction Room (room v10), battery, ML variant. |
| strict_er.sh | (no docstring; read the file) |
| strict_set.py | The user's ask of 2026-11-13: the PTEN and CTL Baseline 10% set without the events that also sit inside the P-spike border. An Ambiguous workflow (the 10% DS border + the P-spike border, applied to the CTL & PTEN pool, no halo), whose DS side is "inside the DS border only"; its X-ray Many folder, read where its events changed; the room's next version; the v7 set put away. Through the app's own routes, in-process. |
| write_leads.py | (no docstring; read the file) |
| write_leads4.py | Run 4 lead lists (2026-11-18): one classifier per recording (the winner), no absolute distances or amplitudes, sink rows left out of "between". |
| write_leads_around.py | -*- coding: utf-8 -*- |
| write_leads_band.py | -*- coding: utf-8 -*- |

## menus

| file | what it says it does |
|---|---|
| explore1.py | (no docstring; read the file) |
| explore2.py | (no docstring; read the file) |
| explore3.py | (no docstring; read the file) |
| explore4.py | (no docstring; read the file) |
| explore5.py | (no docstring; read the file) |
| explore6.py | (no docstring; read the file) |
| figlib.py | House style and shared drawing for the DS story menu (2026-11-23, round 3). |
| j1_battery.py | Jeremy menu, step 2: per-mouse numbers from the frozen DS battery (every Halo DS, 1 kHz, +-50 ms), on the Halo set (v6) and on every filter set (b_*), for Jeremy's questions 1, 2, 3 and 5. Writes jeremy_battery.pkl. |
| j1_battery_before_tight.py | Jeremy menu, step 2: per-mouse numbers from the frozen DS battery (every Halo DS, 1 kHz, +-50 ms), on the Halo set (v6) and on every filter set (b_*), for Jeremy's questions 1, 2, 3 and 5. Writes jeremy_battery.pkl. |
| j2_freq.py | Jeremy menu, step 3: dominant frequency and layer sinks from the 2 kHz X-ray reads (one pipeline for every mouse), for Jeremy's questions 4, 5, 7 and 8. Writes jeremy_freq.pkl. |
| j2_freq_before_tight.py | Jeremy menu, step 3: dominant frequency and layer sinks from the 2 kHz X-ray reads (one pipeline for every mouse), for Jeremy's questions 4, 5, 7 and 8. Writes jeremy_freq.pkl. |
| j_check_ied.py | Check: the red (IED-class) events against the same mice's DS, paired, for every question-7 measure. |
| j_check_und.py | Check: where the undecided events of the Strict workflow sit, per mouse (amplitude, half-width, fast power). |
| j_check_und2.py | Check: what share of each mouse's undecided events are wider than the mouse's median DS half-width. |
| j_explore1.py | (no docstring; read the file) |
| j_explore2.py | (no docstring; read the file) |
| j_explore3.py | (no docstring; read the file) |
| j_merge.py | Merge the Jeremy menu's page PDFs into one document (PyMuPDF; run with miniconda's python). |
| j_package.py | Jeremy menu, last step: copy the pages, write the tables and copy the code into Lab Figures/Jeremy_Menu_112426. Then merge the PDF with miniconda's python: j_merge.py. |
| j_scan.py | Scan the merged Jeremy menu PDF and its tables for words the lab does not use (run with miniconda's python). |
| jfollow.py | Jeremy menu follow-up (2026-11-25): what a held-out call is, and the DS / BT / IED counts per mouse and group. python jfollow.py -> Lab Figures/Jeremy_Menu_Followup_112526 (two pages, merged PDF via j_merge-style pymupdf, CSVs). |
| jpages.py | The Jeremy menu (2026-11-24): Jeremy's eight questions, each answered on its own page that starts with his question word for word ("Jeremy Asked") and a conclusive statement ("Results show"), then an appendix of every mouse in the Strict Root Canal workflow with a summary table and an aggregate. |
| jpages_before_supp.py | The Jeremy menu (2026-11-24): Jeremy's eight questions, each answered on its own page that starts with his question word for word ("Jeremy Asked") and a conclusive statement ("Results show"), then an appendix of every mouse in the Strict Root Canal workflow with a summary table and an aggregate. |
| layer_check.py | Layer check (2026-11-25): every menu result that rests on a layer or a position, computed with the old MML / OML (the average-DS sink, v ranges) and with the tight ones (each DS type's own sink, +-40 um, split at the midpoint; tight_layers.py), side by side. The Jeremy menu itself is not touched. |
| layerax.py | A common depth axis built from each recording's own hand layer labels (StrataScope, in Jarvis). |
| m0_data.py | Story menu, step 0: pull what Jarvis knows into plain files (read only). |
| m10_reads_all.py | Jeremy menu, step 1: read every Halo DS event of the 11 mice that are not IED+ through Jarvis's X-ray reader, with exactly the settings of m2_extract.py (2 kHz, +-100 ms, 5-100 Hz band and notched broadband, refined on the DS-band /CSD/ peak), so that every mouse's DS share one pipeline for the dominant-frequency questions. The five IED+ mice were read by m2_extract.py already (reads/<lab>.npz, every Root Canal event). |
| m1_stats.py | Story menu, step 1: every per-mouse measure through every contrast of the three groupings, with generous uncorrected P (stats_lib), plus the Root Canal measures (DS / in-between / IED classes and their three numbers). Writes tables/all_results.csv and tables/per_mouse_values.csv. |
| m2_extract.py | Story menu, step 2: read every Root Canal event of the five IED+ baseline sessions (and the few in-between / IED events elsewhere) through Jarvis's own X-ray reader, so dentate spikes, in-between events (Twilight Zone) and IEDs come out of ONE pipeline: same contacts, same filters, same alignment. |
| m3_profiles.py | Story menu, step 3: each recording's dentate spike CSD and LFP (the room's X-ray reads, Halo and Strict sets) as mean profiles at the peak, per contact. Used only as the reference for CSD polarity in m4_dsied.py. No layer labels: the scale (ref) is the deepest sink on the dentate rows found from the spike itself (DS-registered depth within 0.6 blade-widths of the two main sinks). Writes profiles_ds.pkl. |
| m4_dsied.py | Story menu, step 4 (round 3): dentate spikes, borderline transients (BTs) and IEDs in the SAME five IED+ sessions, read through one pipeline (m2_extract). Writes dsied.pkl. |
| m6_package.py | Story menu, last step: tables and the folder in Lab Figures (DS_Story_Menu_112326). Run with the plain python for tables (pandas/openpyxl), then merge_pdf.py with miniconda's (PyMuPDF). |
| m7_uprof.py | Story menu, round 3 (2026-11-23 evening): depth from the dentate spike itself, never from the lab's layer labels. |
| m8_timing.py | How close in time DS and BTs sit to IEDs, over windows from 0.25 s to 60 s, against the same events moved to random times (circular shifts within the session, 1,000 per mouse). Writes timing.pkl. |
| m9_tables.py | Round-3 tables (2026-11-23 evening), written into the menu's tables folder by m6_package.py: m7_outlier_tests.csv Grubbs and line outlier tests for m7 (fast power), and every contrast with and without m7 CSD_common_scale_per_mouse.csv Story 3: each mouse's DS current on one common scale, by DS-defined region and sink peak DS_BT_timing_around_IEDs.csv Story 6e: observed over chance counts around IEDs, pooled and per mouse ML_heldout_calls_per_mouse.csv Story 8: each PTEN mouse's held-out calls (IED status, knockout level) and its fast power |
| menu_data.py | Shared data access for the story-menu pages. |
| merge_pdf.py | Merge the eleven page PDFs into one document (PyMuPDF; run with miniconda's python). |
| outlier.py | Is one mouse an outlier? Two standard tests (asked 2026-11-23 for m7 in Story 1). |
| pages_a.py | Story pages 1-4 of the DS story menu (dose, graded dose, place, synchrony). Round 3, 2026-11-23. |
| pages_b.py | Story pages 5-6 of the DS story menu: borderline transients (BTs), and DS vs BT vs IED in the same five IED+ sessions. Round 3, 2026-11-23. |
| pages_c.py | The menu's cover, primer, DS1/DS2 story, ML story and closing page. Round 3, 2026-11-23. |
| poster_ds.py | Poster figure (draft): the IED / DS story in four panels, from the Jeremy menu's data. a DS fast power per mouse, by group b BT and IED-class events per minute, mice in order of knockout c fast power, WT DS / DS / BT / IED d lower-blade MML sink, same classes Written to ../poster/img/ds_story.png at 600 dpi. |
| poster_strip.py | Poster: four small real-data panels under the Isolating Biomarkers steps (Detect, Curate, Align, Classify). One IED+ mouse (m13) for the first three; every Halo event of all 16 mice for the class map. Written to ../poster/img/strip_<n>.png at 300 dpi, each 3.3 x 2.0 in (shown at actual size on the poster). |
| rename_bt.py | Rename the in-between class: pathological dentate spikes (pDS) -> borderline transients (BTs), as decided 2026-11-23. |
| rename_bt2.py | (no docstring; read the file) |
| stats_lib.py | Generous, uncorrected statistics for the story menu (exploratory, as asked 2026-11-23). |
| story_c_v2.py.txt | (no docstring; read the file) |
| story_e_v2.py.txt | (no docstring; read the file) |
| story_e_v3.py.txt | (no docstring; read the file) |
| story_g_v2.py.txt | (no docstring; read the file) |
| tight_layers.py | Layer check (2026-11-25): tight MML / OML contacts per recording, from each DS type's own sink. |
| wf_probe.py | Look inside the Halo workflow's saved run (Root Canal workflow 6fa7fef7b7a3 v5): what per-event columns does it keep? |

## poster

| file | what it says it does |
|---|---|
| assets.py | Image assets for the poster, cut from the Jan-26 poster's pictures (python assets.py). p7_timeline.png the P7 injection -> electrophysiology schematic, without the Pten;Raptor genotype line traces_wt_ko.png the Wildtype and Pten KO current-clamp traces with the original 20 mV / 200 ms scale bar moved beside them theta_A.png theta CSD rasters with the PTEN/RAPTOR raster (old Aiii) cut out; old Aiv relabeled Aiii icon_*.png emoji icons for the biomarker steps |
| build.py | Build the 48 x 36 in PTEN poster in the UVM theme (python build.py, after assets.py and the menu's poster_ds.py and poster_strip.py). Jan-26 figures come back for theta (A), IED initiation (B, C) and CNO (D); the DS story (E) is a new draft figure; Behavior (F) and the writing sections are placeholders. |
| mid.py.txt | (no docstring; read the file) |
