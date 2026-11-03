-- ===========================================================================
-- BARRY GUI -- migration 19: the request budget
--
-- Run after 01-18. Idempotent. Until it is run the app works exactly as
-- before: the machine row's `jarvis_version` is dropped and retried (one
-- refused request per start), and `errors` / `error_marks` are pulled every
-- ten minutes instead of when they change.
--
-- Part of the Supabase overhaul (GUI-CONSTITUTION.md section 11). The free
-- tier went 192% over its egress allowance and 1,148% over log ingestion in
-- September 2026, and both track the number of requests. Two things here:
--
-- 1. `machines.jarvis_version` -- which code each computer runs. One rig
--    that has not pulled keeps making the old requests for everybody, and
--    nothing said which one it was. The app sends it with the machine
--    heartbeat and /api/devices shows it.
--
-- 2. `errors` and `error_marks` in the watermark view. Migration 17 left
--    them out, and the pull skips any table the view does not say moved --
--    so from migration 17 on, error triage made on one machine never
--    reached another. Listed here, they cost nothing until they change.
-- ===========================================================================

alter table public.machines
  add column if not exists jarvis_version text;

comment on column public.machines.jarvis_version is
  'The app version and commit this computer last reported, e.g. '
  '2026.09.29.4+a1b2c3d. Sent with the five-minute heartbeat.';

-- max(updated_at) is what the view asks of every table; without an index it
-- reads the whole of `errors` (thousands of rows) on every quiet pull.
create index if not exists errors_updated_idx      on public.errors (updated_at);
create index if not exists error_marks_updated_idx on public.error_marks (updated_at);

-- ---------------------------------------------------------------------------
-- The watermark view, as migration 18 left it, plus the two error tables.
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
  union all select 'tool_results',      max(updated_at) from public.tool_results
  union all select 'artifacts',         max(updated_at) from public.artifacts
  union all select 'artifact_snapshots', max(updated_at) from public.artifact_snapshots
  union all select 'errors',            max(updated_at) from public.errors
  union all select 'error_marks',       max(updated_at) from public.error_marks;

comment on view public.barry_watermarks is
  'The newest updated_at in each synced table, so a client can ask one '
  'question instead of one per table. A table missing from this view is '
  'one a pull cannot trust itself to skip -- add every new synced table '
  'here in the migration that creates it.';

grant select on public.barry_watermarks to anon, authenticated, service_role;
