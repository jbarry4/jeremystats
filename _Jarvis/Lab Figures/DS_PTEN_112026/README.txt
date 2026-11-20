DS / PTEN results as of 2026-11-20 (battery run 5, ML run r006)

Data: Extraction Room "Dentate Spike" v9 (Halo set, 4,733 events, 18 recordings), after
  - 103 duplicate Spike stamps (two stamps on one event, under 10 ms apart) were marked Garbage, and
  - m1 s2 was put back on its Lock alignment.
m6 is left out; m51 has 5 events and is left out of statistics.

battery_reports/    the test battery (uncorrected leads, corrected tables). Run 5: Halo set = room v9;
                    Strict set = room v10 (10% grace border, no halo, P-spike border removed; 3,905
                    events in the 16 analyzed recordings), read through the Extraction Room.
round11/            sanity check, averaged DS1/DS2, summary table, supplement, quality-check pages
room2_preliminary/  Extraction Room 2.0 (machine learning) methods and results, run r006 (Halo set,
                    16 mice; m21 is in, with no DS type: no classifier keeps 5 events of each type
                    once its duplicate stamps are gone)
room2_figures/      the same as journal-style figures, run r006
duplicate_check/    the duplicate stamps, drawn for checking by eye

Nothing here is corrected for the number of models or tests unless the file name says "corrected".
