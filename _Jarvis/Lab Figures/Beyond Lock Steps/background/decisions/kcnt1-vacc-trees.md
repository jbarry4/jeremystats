# kcnt1-vacc-trees

_Where the KCNT1 urethane data lives on the VACC, and which file is the authority on whether a session is usable._

The KCNT1 urethane dataset on the VACC is two trees under
`/gpfs2/scratch/sakhava1/KCNT1 Urethane/`: `KCNT1_DATA` (9 sessions, owned by
`erachimi`, carrying 13-14 `.mat` sidecars each) and `KCNT1_DATA_NEW`
(9 sessions, 3 sidecars each). 18 sessions, 205 GB, all 128 channels at
30 kHz and all intact as raw data. Scratch is purge-eligible. When this was
written `/netfiles/bigdata_jbarry` was permission-denied to this netid; since
2026-10-01 it reads (see [vacc-reads-netfiles](vacc-reads-netfiles.md)), and it holds a
`urethane/` tree of its own -- check there before calling scratch the only
copy.

Whether a session is *usable* is not a filesystem fact. Two files agree
exactly on the same 13 sessions and are the authority:

  `Take 2/Output2/(Drive id on the work PC)/AggSpikes_Master_Stats.csv`
      status `OK` vs `NO_SOLIDS`
  `Take 2/LAMINAR_LABLING_DATA/`
      one folder per session that got laminar labels

The five that fail are M5s2, M10s2, M11s6, M13s3 and M17s2 — all
`NO_SOLIDS`: IEDs were detected (4 to 300 of them) but none survived review.
Four of them are the Controls in KCNt14Shahriar.xlsx, so no surviving IED is
the expected answer, not a failure (M17s2 is not on the sheet). See
`kcnt1-urethane-analysis-set` (a note not copied here).

**Why:** the folder listing gives 18 equally healthy-looking sessions, and
nothing in the raw files distinguishes the 13 from the 5. Deciding validity
by scanning NCS files alone gets the wrong answer.

**How to apply:** join on the session folder name (`Kcnt1_M<m>s<s>`), and
normalise `Kcnt1_M19s4_old` — how `Extra Stats/Stats Output/IED_counts_per_session.csv`
spells M19s4 — to `Kcnt1_M19s4` first. Genotype is recorded nowhere in
either tree. `Kcnt1_M14s2` holds 62 recording folders of which only
`2022-10-19_15-47-43` has samples; the other 61 are header-only stubs, every
CSC file exactly 16384 bytes. See [kcnt1-vacc-copies-are-single-part](kcnt1-vacc-copies-are-single-part.md) and
[mouse-session-is-not-an-identity](mouse-session-is-not-an-identity.md).
