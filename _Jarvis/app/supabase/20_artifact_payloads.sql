-- ===========================================================================
-- BARRY GUI -- migration 20: artifact payloads, small enough to send
--
-- Run after 01-19, straight after restarting the project. Idempotent.
--
-- Why
-- ---
-- From 2026-09-30 the database kept going down (Cloudflare 520/521/522 for
-- every request). Each time it started with a push to `artifact_snapshots`
-- that timed out: up to two hundred artifact payloads in one request, some
-- of them 10 MB of JSON, into a free-tier instance with half a gigabyte of
-- memory. The payloads also travel in git, so EVERY machine had them and
-- every machine sent the same request again as soon as the database came
-- back, which took it down again.
--
-- What this does
-- --------------
-- 1. Renames `artifact_snapshots` to `artifact_snapshots_retired`. A Jarvis
--    that has not been updated finds the table gone, treats it as "migration
--    not run", and stops sending payloads -- with no change on that machine.
--    The rows are kept; see the end of this file for reclaiming the space.
-- 2. Creates `artifact_payloads`: the same key, the payload gzipped and
--    base64'd into a text column (`gz`). These payloads are numbers and
--    compress 10-18x (290 MB of JSON is 28 MB gzipped). Updated Jarvis sends
--    them one bounded request at a time and fetches them one key at a time,
--    never two hundred in one answer.
-- 3. Puts `artifact_payloads` in the watermark view in place of the old one.
-- ===========================================================================

alter table if exists public.artifact_snapshots
  rename to artifact_snapshots_retired;

create table if not exists public.artifact_payloads (
  artifact_id  text        not null references public.artifacts(id)
                                     on delete cascade,
  version_id   text        not null,
  v            integer,
  -- The version's own digest (sha1 of the canonical payload, 12 hex).
  -- Checked on arrival against the decoded payload and the version row.
  digest       text,
  bytes        integer,                -- size of the JSON before gzip
  gz           text        not null,   -- base64 of gzip of compact JSON
  machine      text,
  updated_at   timestamptz not null default now(),
  primary key (artifact_id, version_id)
);
create index if not exists artifact_payloads_updated_idx
  on public.artifact_payloads (updated_at);

alter table public.artifact_payloads enable row level security;
revoke all on public.artifact_payloads from anon;

-- Written once, like the table it replaces: an upsert that finds the key
-- keeps what is there (barry_add_only is from migration 18).
drop trigger if exists artifact_payloads_add_only on public.artifact_payloads;
create trigger artifact_payloads_add_only
  before update on public.artifact_payloads
  for each row execute function barry_add_only();

comment on table public.artifact_payloads is
  'Each artifact version''s payload, gzipped and base64''d into `gz`. '
  'Append-only by trigger. Replaces artifact_snapshots (migration 20), '
  'whose plain-JSON payloads, sent two hundred at a time, took the '
  'database down.';

-- ---------------------------------------------------------------------------
-- The watermark view, as migration 19 left it, with artifact_payloads in
-- place of artifact_snapshots.
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
  union all select 'artifact_payloads', max(updated_at) from public.artifact_payloads
  union all select 'errors',            max(updated_at) from public.errors
  union all select 'error_marks',       max(updated_at) from public.error_marks;

grant select on public.barry_watermarks to anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- How big is the old table? Run this to see. The free tier allows 500 MB
-- of database in all.
--
--   select pg_size_pretty(pg_total_relation_size('public.artifact_snapshots_retired'))
--          as retired, pg_size_pretty(pg_database_size(current_database())) as whole_db;
--
-- Nothing in it is lost by dropping it: every payload is also in git
-- (GUI_logs/artifacts/snap/) and updated Jarvis re-sends them, compressed,
-- into artifact_payloads. When the database is near its limit, reclaim it:
--
--   drop table if exists public.artifact_snapshots_retired;
-- ---------------------------------------------------------------------------
