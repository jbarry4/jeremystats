-- ===========================================================================
-- 17 -- Which probe went into the animal, and one cheap question about the
--       whole database.
--
-- Two unrelated things in one migration because they are one deployment, and
-- a migration somebody has to remember to run twice is a migration that gets
-- run once.
--
-- ---------------------------------------------------------------------------
-- PART ONE: the probe
-- ---------------------------------------------------------------------------
-- A recording's probe decides how its array is divided into lines of
-- contacts, and a CSD is only meaningful down one line. On the lab's KCNT1
-- recordings there are two implants -- hippocampus on CSC 1-64, M2 on 65-128 --
-- so a CSD down the channel order steps across the gap at channel 64 and
-- subtracts cortex from hippocampus. It produces a number, the number means
-- nothing, and nothing about it looks wrong.
--
-- That fact lived in one window's view state, so it lasted as long as that
-- window and travelled to nobody. Here it travels.
--
-- `probe_source` carries the distinction the whole design rests on:
--   'manual'   somebody said so
--   NULL       nobody has, and the app is reading it from the channel count
-- A guess written into `probe` would be indistinguishable from an answer
-- afterwards, which is the one thing that must not happen -- 70 of the 71
-- dual implants in this lab are currently guesses.
--
-- `channel_banks` is the per-bank region map that goes with it, merged by
-- id locally (`shards.BYID`) so two people labelling two banks both keep
-- their work. Stored as jsonb because it is a small list of small objects
-- and nothing queries inside it.
-- ---------------------------------------------------------------------------

alter table public.sessions
  add column if not exists probe          text,
  add column if not exists probe_source   text,
  add column if not exists channel_banks  jsonb;

comment on column public.sessions.probe is
  'Probe template id: h3, h10d, dual. NULL means nobody has said -- which '
  'is NOT the same as h3, and the difference decides whether a CSD is run '
  'down one line of contacts or across two brain regions.';
comment on column public.sessions.probe_source is
  '''manual'' when a person set it. NULL when nobody has. A guess is never '
  'written here; the app derives one from the channel count at read time '
  'so that it stays visibly a guess.';
comment on column public.sessions.channel_banks is
  'Blocks of 64 channels and what each one is, e.g. '
  '[{"id":"b1","first":1,"last":64,"region":"Hippocampus"}]. Region is null '
  'until a person says.';

-- Finding the unconfirmed ones is the daily question, and it is a small
-- fraction of the table -- so a partial index rather than a full one.
create index if not exists sessions_probe_unset_idx
  on public.sessions (gid)
  where probe is null;

-- ---------------------------------------------------------------------------
-- PART TWO: one question instead of twenty-one
-- ---------------------------------------------------------------------------
-- Measured, not guessed. The app pulls every 20 seconds and asks each of
-- twenty-one tables "anything newer than X". On a quiet cycle every one of
-- them answers "no", which is 21 requests, 90,720 a day per machine, and
-- about 6.5 GB of egress a month against a 5 GB allowance -- while the rows
-- themselves came to 7 KB a cycle.
--
-- So the bytes were never the problem. The REQUESTS were.
--
-- This view answers all twenty-one at once: one row per table, carrying the
-- newest `updated_at` in it. A quiet cycle becomes a single request that
-- returns a few hundred bytes, and a busy one fetches only the tables that
-- actually moved.
--
-- Written as a view rather than a trigger-maintained table on purpose: a
-- watermark table is a second source of truth that can drift, and the whole
-- point of this is to be trusted enough to skip work on.
-- ---------------------------------------------------------------------------

create or replace view public.barry_watermarks as
  select 'machines'          as table_name, max(updated_at) as updated_at from public.machines
  union all select 'sessions',          max(updated_at) from public.sessions
  union all select 'session_paths',     max(updated_at) from public.session_paths
  union all select 'session_sightings', max(updated_at) from public.session_sightings
  union all select 'mice',              max(updated_at) from public.mice
  union all select 'bank_entries',      max(updated_at) from public.bank_entries
  union all select 'bank_snapshots',    max(updated_at) from public.bank_snapshots
  union all select 'curation_sets',     max(updated_at) from public.curation_sets
  union all select 'curation_events',   max(updated_at) from public.curation_events
  union all select 'curation_reviews',  max(updated_at) from public.curation_reviews
  union all select 'layer_sheets',      max(updated_at) from public.layer_sheets
  union all select 'layer_labels',      max(updated_at) from public.layer_labels
  union all select 'storyboards',       max(updated_at) from public.storyboards
  union all select 'results',           max(updated_at) from public.results
  union all select 'presets',           max(updated_at) from public.presets
  union all select 'prefs',             max(updated_at) from public.prefs
  union all select 'feedback',          max(updated_at) from public.feedback
  union all select 'feedback_notes',    max(updated_at) from public.feedback_notes
  union all select 'people',            max(updated_at) from public.people
  union all select 'health_checks',     max(updated_at) from public.health_checks
  union all select 'tool_results',      max(updated_at) from public.tool_results;

comment on view public.barry_watermarks is
  'The newest updated_at in each synced table, so a client can ask one '
  'question instead of twenty-one. A quiet sync cycle is then a single '
  'request rather than a sweep -- which is the difference between 6.5 GB '
  'of egress a month and a few hundred MB.';

grant select on public.barry_watermarks to anon, authenticated, service_role;
