# Background: decisions from the work PC's Claude memory (copied 2026-11-27)

These are the notes Claude kept on the work PC while building the PTEN pipeline. They record the user's answers
and the reasons behind each choice. Treat them as background, true when written; check against the code and data.
Drive ids, links and email addresses were taken out (this folder is in a public repo).

## pipeline

- [the-confluence-decisions](the-confluence-decisions.md): The Confluence bundle (Incisor + Doppler pooled): the user's 10 answers and the calls made building it, 2026-10-14.
- [lock-is-braces](lock-is-braces.md): Lock (Confluence step 3) is Braces built twice via makeBraces(cfg) since 2026-10-22; Panning-only input; origin groups (Incisor only/Merged/Doppler only) choose what moves, the rest held; DS band default; pickers are tiles, never radios
- [m1-lock-undone-by-panning](m1-lock-undone-by-panning.md): Audit 2026-11-19: every battery/ER2 event comes from the newest Lock version of its Confluence entry, except PTEN m1 s2, whose Lock (v2) was undone 6 min later by Panning's bank-on-leave (v3 = v1).
- [rootcanal-workflow-decisions](rootcanal-workflow-decisions.md): Root Canal "Workflow" tab (asked 2026-11-05) — three separate workflows (verified DS / verified P-spikes / ambiguous), Define → Apply → Extract, and the user's 10 answers.
- [rootcanal-meta-workflow](rootcanal-meta-workflow.md): Root Canal "Meta Workflow" (2026-11-11) — searches measurement settings to minimise purple (ambiguous) under the Ambiguous Dataset's two boxes; the user's 5 answers.
- [rootcanal-border-shapes](rootcanal-border-shapes.md): Root Canal border shapes (2026-11-11) — Box / Scoop (robust ellipsoid) / Snap (convex hull), workflow folders, the 18 shape workflows and their purple counts.
- [halo-biteline-impression-decisions](halo-biteline-impression-decisions.md): 2026-11-12 round: Halo (capture outside both), the new room round without X-ray, the Bite line split, Compare splits, Impression lock, Blob Analysis — the user's 20 answers.
- [camel-hump-is-bookkeeping](camel-hump-is-bookkeeping.md): The "camel hump" (a notch inside a sink hump) was per-event top-2 bump bookkeeping, not bad channels; fixed 11-12 with sinkcut sink="humps". Off-gain contacts 25/49 in mid-2024 PTEN sessions.
- [room-sets-lineage](room-sets-lineage.md): What each Extraction Room set is built from (workflow → pools → X-ray Many folder → room version), checked event by event 2026-11-13; why the "CTL Baseline" set holds PTEN.
- [xray-many-decisions](xray-many-decisions.md): X-ray Many + Novocaine (asked 2026-11-07): folders of Verified DS 5%/10% sets, per-recording box on each average CSD, ΔBIC+10% separation, versioned bundles, Novocaine liminal space later.
- [compare-splits-fifteen](compare-splits-fifteen.md): Compare splits since 2026-11-13: 5 methods (delta middle added) × 3 rows (both humps / top only / bottom only) and a low-contacts toggle that is a look only.
- [ds3-trim-mixup-decisions](ds3-trim-mixup-decisions.md): 2026-11-13: the user's 32 answers for DS3 (Tarcsay relative-sink score), the probability trim, the mix-up sanity check, and the room redesign (5x3 Compare grid, cards tidied).
- [extraction-room-decisions](extraction-room-decisions.md): The Extraction Room (Dentist step 6, web/extraction.html) — what the user asked for, the label misread, and where the first results landed (2026-11-10)
- [extraction-room-2-decisions](extraction-room-2-decisions.md): 2026-11-18: Extraction Room 2.0 = ML models over frozen DS sets (tab 'Room 2.0 · models'); the user's 20 answers; where the code and data live.
- [ds-pten-halo-and-strict-sets](ds-pten-halo-and-strict-sets.md): 2026-11-20: the two DS/PTEN event sets are "Halo" and "Strict" (never "No P-spikes"); room v9/v10 after dedupe; m21 stays in the ML with no DS type.
- [project-evolve](project-evolve.md): PROJECT EVOLVE (2026-11-18): Rain's Planning Doc → Jarvis plan; 50 answers; built phase by phase (outline → feedback → build → user checks in Jarvis → cross off). DS work first, Kilosort last.
- [rootcanal-reads-are-machine-local](rootcanal-reads-are-machine-local.md): Root Canal reads (.npz), Incisor scans and Doppler runs live in gitignored GUI_logs/.cache; since 2026-10-30 the app copies them to the VACC answers shelf and fetches on a miss -- but only the app process, never tools/checks.

## analysis and menus

- [ds-pten-deep-round-1116](ds-pten-deep-round-1116.md): 2026-11-16 deep round on the Halo set: 240 tests give nothing after correction; DS1/DS2 resolve in 6 of 17 recordings (DS1 ~8%, outer by ~160 um, 0.4x sink); one lead (granule-layer source weakens with knockout). Figures on the Desktop.
- [ds-pten-m6-excluded-and-figure-rules](ds-pten-m6-excluded-and-figure-rules.md): 2026-11-17 standing rules for the DS/PTEN pilot: m6 is out (experiment confounds); the user makes the separable call; no folded or "main sink" figures; explain every axis.
- [ds-story-menu-1123](ds-story-menu-1123.md): 2026-11-23 DS story menu (Lab Figures/DS_Story_Menu_112326): the user's answers (BT name, three groupings, generous stats, staged dose/place/synchrony frame, DS-registered depth, common CSD scale), round-3 revisions, and the main findings.
- [story-menu-figure-rules](story-menu-figure-rules.md): 2026-11-23 rules for story-menu figures (Lab Figures menus): finding headings, star brackets that never touch a line, CSDs on one scale across groups, depth always on y, no lab layer labels, fit lines and bands, significance bars on line plots, every mouse on scale.
- [jeremy-menu-1124](jeremy-menu-1124.md): 11-24 Jeremy menu: Jeremy's 8 DS questions, one page each ("Jeremy Asked" verbatim, then "Results show" conclusive), plus a Strict-workflow every-mouse appendix; where it lives, the choices made, what it found.
- [layer-check-1125](layer-check-1125.md): 11-25 layer check: the Jeremy menu's MML/OML were anchored on the all-DS (mixed DS1+DS2) sink; tight rule = DS2 sink is MML, DS1 sink is OML, +-40 um, midpoint split; old-vs-tight report in Lab Figures/Layer_Check_112526; menu not updated yet.
- [kcnt1-poster-decisions](kcnt1-poster-decisions.md): KCNT1 AES poster, first pass 2026-11-25: the lab's PTEN poster is the house template (48x36), three columns, 'failing dentate gate' title, Shahriar first author, DS-vs-IED left out, behavior = all 56 mice.

## data facts

- [pten-probe-is-h3-20um](pten-probe-is-h3-20um.md): PTEN/CTL/DKO linear-probe recordings are H3 (64 ch, 20 um pitch); even contacts are 40 um apart, not 100. csc.compute_csd's 50 um default is wrong for them.
- [mains-is-inside-the-ds-band](mains-is-inside-the-ds-band.md): 60 Hz sits inside the 5-100 Hz DS band and a CSD cannot reject it; notch before timing anything.
- [ied-hand-sorts-are-on-concat-time](ied-hand-sorts-are-on-concat-time.md): The PTEN IED hand-sort stamps in the bank are concatenated-sample seconds, not true seconds; Doppler answers in true seconds — map before scoring
- [bank-keys-on-the-registry-gid](bank-keys-on-the-registry-gid.md): Event bank and curation sets key on the registry's session gid (sXXXXXXXXXXXX), not on ids.identify()'s identity string — matching a recording folder to banked data by identity silently returns zero.
- [bank-identifies-events-by-time](bank-identifies-events-by-time.md): A banked event's identity IS its time, so anything that moves a stamp must carry from_t or the version diff reads as a total replacement.
- [a-set-made-twice-doubles](a-set-made-twice-doubles.md): A curation set created on a machine that has not pulled it mints fresh event ids; the shard merge unions them and every event appears twice.
- [mouse-session-is-not-an-identity](mouse-session-is-not-an-identity.md): Mouse+session numbering restarts per project in this lab, so m1 s1 exists many times; anything matching on loose_key alone can merge two recordings.
- [kcnt1-ds-groups-1125](kcnt1-ds-groups-1125.md): KCNT1 awake DS readiness 2026-11-25: genotype is column 'YH' on the DS Data sheet; 8 Locked (WT 3 F, Het 3 M, Hom 2 F); WT is the bottleneck and sex is confounded.
- [kcnt1-m531-probe-by-session](kcnt1-m531-probe-by-session.md): KCNT1 m531 (2026-07-22): s1 recorded with the H3 Cheetah config and its signal looks linear; s2–s7 used the H10-D config and look H10. Checked 2026-11-20.
- [kcnt1-vacc-trees](kcnt1-vacc-trees.md): Where the KCNT1 urethane data lives on the VACC, and which file is the authority on whether a session is usable.
- [kcnt1-vacc-copies-are-single-part](kcnt1-vacc-copies-are-single-part.md): On the VACC copies the _0001 suffix is a naming artifact, not a continuation file — unlike the local copies.
- [header-only-folders-are-not-recordings](header-only-folders-are-not-recordings.md): Stub folders (every CSC 16384 B) hid real recordings: a record keyed on a stub got retired 'no data' (m531 s1 in Sessions, not Incisor). Fixed 11-03/04: prune tool, upsert_session refuses stub paths, audit judges every folder, retire refuses data, REG.live().

## words

- [never-say-a-spike](never-say-a-spike.md): The user bans one name for the in-between class (a letter in front of "-spike"); the purple class reads "Twilight Zone" on screen and "BTs" in figures.
- [ied-is-p-spike](ied-is-p-spike.md): Since 2026-11-05 every user-visible "IED" says "P-spike"; DS blue (--call-ds), P-spikes red (--call-p); stored id stays 'ied'.
- [exploratory-no-correction](exploratory-no-correction.md): 2026-11-21: DS/PTEN is exploratory — report raw P values and effects normally; no multiple-comparison correction, family-wise P, q values or 'only a lead' hedging.
- [american-spelling](american-spelling.md): Write American English everywhere (optimized, normalized, color, center, gray, analyzed) — replies, figures, captions, UI text.
- [never-truncate-text](never-truncate-text.md): Shahriar's rule for BARRY GUI - never cut text with an ellipsis; shrink the type or reflow the layout instead.

## working on the lab PCs

- [the-repo-is-public](the-repo-is-public.md): jbarry4/jeremystats on GitHub is PUBLIC (checked 2026-11-05 via the unauthenticated API); secrets travel through the Supabase key, never git.
- [another-agent-may-commit-your-work](another-agent-may-commit-your-work.md): This repo is sometimes worked by two Claude sessions at once; the other one makes blanket commits that sweep in your work, and can restore a shared file from git and erase your uncommitted edits to it.
- [no-js-through-shell-heredocs](no-js-through-shell-heredocs.md): Never write JS/regex through a shell heredoc in this project — write the patch script with the Write tool instead.
- [a-server-only-lives-inside-its-tool-call](a-server-only-lives-inside-its-tool-call.md): A Flask server started with PowerShell Start-Process dies when that tool call returns, and Bash run_in_background reports exit 127 for it while it is actually running — so start the server and run the harness in ONE PowerShell call.
- [piped-server-log-deadlocks](piped-server-log-deadlocks.md): A test server started with stdout=PIPE stops answering after ~40 requests, and it reads as a slow route.
- [time-routes-after-startup-settles](time-routes-after-startup-settles.md): Timing a backend route right after importing backend.app reads 10-20x slow; the start-up threads (warm, bank mirror, prewarm) contend for about 30-40 s.
- [first-importer-pays](first-importer-pays.md): Heavy libraries in backend/ go through lazyimp.py; making one module lazy just moves the cost to the next importer. cfc.py is the exception.
- [scripts-must-wire-the-profile](scripts-must-wire-the-profile.md): A bare storemod.Store in a script stamps records with the git identity, not the user's profile; wire Profile and Device onto it before writing.
- [python-open-truncates-before-it-raises](python-open-truncates-before-it-raises.md): io.open(path, "w", newline=<bad>) empties the file and THEN raises; a patch script with a bad argument destroyed spotter.js
- [measure-dont-guess](measure-dont-guess.md): On BARRY GUI, diagnose UI complaints with a purpose-built browser harness rather than reading CSS or judging by eye.
- [vacc-reads-netfiles](vacc-reads-netfiles.md): Since 2026-10-01 sakhava1 can read AND write /netfiles/bigdata_jbarry on the VACC (group jarvis_writes); compute nodes see it too. 1,461 recordings there.
- [vacc-upload-speed-is-per-stream](vacc-upload-speed-is-per-stream.md): One ssh stream to the VACC login node carries ~10 MB/s; parallel streams scale (4 → 52, 8 → 89 MB/s), measured 2026-10-01
- [vacc-temp-has-a-1tb-quota](vacc-temp-has-a-1tb-quota.md): gpfs3tmp ("Temp", Jarvis_temp) is NOT unlimited — pi-jbarry4's group quota there is 1000 GB (hard 1010), and on 2026-10-01 it was full
- [vaccsignin-can-leave-you-signed-out](vaccsignin-can-leave-you-signed-out.md): _dev/vaccsignin.html signs the machine out and back in by netid; if the key check fails mid-suite it stays signed out (GUI_logs/.vacc.json loses netid/key_path).
- [machine-has-two-names](machine-has-two-names.md): In BARRY, the same computer has several identifiers — provenance().machine, its host, and the shard/hostname id — and comparing the wrong one passes vacuously.
