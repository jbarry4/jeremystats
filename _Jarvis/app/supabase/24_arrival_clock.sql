-- ===========================================================================
-- 24 -- the arrival clock (2026-10-30)
--
-- Run once, in the SQL editor. Safe to run again.
--
-- WHY. Every synced row carries `updated_at`, stamped by the computer that
-- wrote it, and each computer pulled "everything newer than the newest
-- `updated_at` I have seen". That cursor races ahead of rows still on their
-- way: a bank made on Strawbarry at 10:00:00 and pushed at 10:00:40 was never
-- pulled by a Bluebarry whose cursor had already reached 10:00:20 -- from its
-- own rows coming back, or anybody else's. The watermark view could not see
-- it either, because a late row with an older stamp does not move a max.
-- That is "results banked in Panning don't show up unless a github sync is
-- done": git carried the shard, the database had the row, and no pull ever
-- asked for it.
--
-- WHAT. Every synced table gets `synced_at`: the DATABASE's clock when a row
-- arrived or changed, set here and never sent. The watermark view carries
-- its max beside `updated_at`, lists `shard_files` (which it never did, so
-- Braces sets and AI Beta runs were asked about only every ten minutes),
-- and adds a `_clock` row with the database's own time, which is what a
-- pull keeps as its cursor. `updated_at` still decides which write wins
-- (barry_keep_newest); `synced_at` only decides what to ask for.
--
-- AFTER. Nothing to do on the machines. Jarvis reads the view and switches
-- itself over; its first pull on the new clock reads every table once from
-- the beginning, which is what brings back every row the old cursor missed.
-- ===========================================================================

-- And two things an entry's live set carries that never travelled: what it
-- is aligned to (Root Canal waits for it) and its label mix. Jarvis sends
-- them once these exist and leaves them out until then.
alter table public.bank_entries add column if not exists aligned  jsonb;
alter table public.bank_entries add column if not exists by_label jsonb;

-- Set on every insert, and on an update that actually changed the row.
-- Fires after `<table>_keep_newest` (triggers run in name order, and
-- `_zz_arrival` sorts last): when that one keeps the row that was there,
-- nothing changed, and the arrival time stays what it was -- or a stale push
-- would make an old row look new to every machine.
create or replace function barry_arrival()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'INSERT' then
    new.synced_at := clock_timestamp();
  elsif (to_jsonb(new) - 'synced_at') is distinct from
        (to_jsonb(old) - 'synced_at') then
    new.synced_at := clock_timestamp();
  else
    new.synced_at := old.synced_at;
  end if;
  return new;
end;
$$;

do $$
declare
  t text;
begin
  foreach t in array array[
    'machines', 'sessions', 'session_paths', 'session_sightings', 'mice',
    'bank_entries', 'bank_snapshots', 'curation_sets', 'curation_events',
    'curation_reviews', 'layer_sheets', 'layer_labels', 'storyboards',
    'results', 'presets', 'prefs', 'feedback', 'feedback_notes', 'people',
    'health_checks', 'tool_results', 'artifacts', 'artifact_payloads',
    'errors', 'error_marks', 'shard_files'
  ]
  loop
    if to_regclass('public.' || t) is null then
      raise notice 'skipped %, which this database does not have', t;
      continue;
    end if;
    execute format(
      'alter table public.%I add column if not exists synced_at '
      'timestamptz not null default now()', t);
    execute format(
      'create index if not exists %I on public.%I (synced_at)',
      t || '_synced_idx', t);
    execute format(
      'drop trigger if exists %I on public.%I', t || '_zz_arrival', t);
    execute format(
      'create trigger %I before insert or update on public.%I '
      'for each row execute function barry_arrival()',
      t || '_zz_arrival', t);
  end loop;
end;
$$;

-- The same rows as migration 20's view, in the same order, with `synced_at`
-- added at the end of each and two rows more: `shard_files`, and `_clock`.
create or replace view public.barry_watermarks as
  select 'machines'          as table_name, max(updated_at) as updated_at, max(synced_at) as synced_at from public.machines
  union all select 'sessions',          max(updated_at), max(synced_at) from public.sessions
  union all select 'session_paths',     max(updated_at), max(synced_at) from public.session_paths
  union all select 'session_sightings', max(updated_at), max(synced_at) from public.session_sightings
  union all select 'mice',              max(updated_at), max(synced_at) from public.mice
  union all select 'bank_entries',      max(updated_at), max(synced_at) from public.bank_entries
  union all select 'bank_snapshots',    max(updated_at), max(synced_at) from public.bank_snapshots
  union all select 'curation_sets',     max(updated_at), max(synced_at) from public.curation_sets
  union all select 'curation_events',   max(updated_at), max(synced_at) from public.curation_events
  union all select 'curation_reviews',  max(updated_at), max(synced_at) from public.curation_reviews
  union all select 'layer_sheets',      max(updated_at), max(synced_at) from public.layer_sheets
  union all select 'layer_labels',      max(updated_at), max(synced_at) from public.layer_labels
  union all select 'storyboards',       max(updated_at), max(synced_at) from public.storyboards
  union all select 'results',           max(updated_at), max(synced_at) from public.results
  union all select 'presets',           max(updated_at), max(synced_at) from public.presets
  union all select 'prefs',             max(updated_at), max(synced_at) from public.prefs
  union all select 'feedback',          max(updated_at), max(synced_at) from public.feedback
  union all select 'feedback_notes',    max(updated_at), max(synced_at) from public.feedback_notes
  union all select 'people',            max(updated_at), max(synced_at) from public.people
  union all select 'health_checks',     max(updated_at), max(synced_at) from public.health_checks
  union all select 'tool_results',      max(updated_at), max(synced_at) from public.tool_results
  union all select 'artifacts',         max(updated_at), max(synced_at) from public.artifacts
  union all select 'artifact_payloads', max(updated_at), max(synced_at) from public.artifact_payloads
  union all select 'errors',            max(updated_at), max(synced_at) from public.errors
  union all select 'error_marks',       max(updated_at), max(synced_at) from public.error_marks
  union all select 'shard_files',       max(updated_at), max(synced_at) from public.shard_files
  union all select '_clock',            now(),           now();

comment on view public.barry_watermarks is
  'The newest updated_at and synced_at in each synced table, plus the '
  'database''s own time (_clock). A pull asks by synced_at -- when a row '
  'ARRIVED -- so a row pushed late is still seen (migration 24).';

grant select on public.barry_watermarks to anon, authenticated, service_role;
