DS / PTEN results as of 2026-11-23 (battery run 5, ML runs r006 to r017)

Data: Extraction Room "Dentate Spike" v9 (Halo set, 4,733 events, 18 recordings), after
  - 103 duplicate Spike stamps (two stamps on one event, under 10 ms apart) were marked Garbage, and
  - m1 s2 was put back on its Lock alignment.
m6 is left out; m51 has 5 events and is left out of statistics.

battery_reports/    the test battery (per-test results). Run 5: Halo set = room v9;
                    Strict set = room v10 (10% grace border, no halo, P-spike border removed; 3,905
                    events in the 16 analyzed recordings), read through the Extraction Room.
round11/            sanity check, averaged DS1/DS2, summary table, supplement, quality-check pages
room2_preliminary/  Extraction Room 2.0 (machine learning) methods and results, run r006 (Halo set,
                    16 mice; m21 is in, with no DS type: no classifier keeps 5 events of each type
                    once its duplicate stamps are gone)
room2_figures/      the same as journal-style figures, run r006
duplicate_check/    the duplicate stamps, drawn for checking by eye



Added 2026-11-23
ml_runs/                          all ML runs r006 to r017 (leaderboards) and ML_summary.txt in plain text:
                                  DS1 vs DS2, DS1 minus DS2 per mouse, one DS type at a time with random
                                  twins, and all events with the raw event (CSD, LFP, spectrogram).
Dentate_spikes_what_we_found.html the summary deck (12 slides; open in a browser; double-click shows notes).
Exploratory pilot: P values are per test.
