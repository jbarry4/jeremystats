-- ===========================================================================
-- BARRY GUI -- migration 18: Jarvis Artifacts
--
-- Run after 01-17. Idempotent. Until it is run, the app sends and takes no
-- artifact rows and says nothing about it: a push finds the table absent and
-- sends nothing, and a pull skips it.
--
-- An artifact is a versioned thing a stage makes and a later stage reads --
-- a Circuit (one recording, one cue type, one kind) that a Drift averages.
-- See backend/artifacts.py. Two tables, shaped like the bank's two:
--
--   artifacts           the record: identity, name, nickname, the version
--                       list (metadata only), who cites what, deleted.
--   artifact_snapshots  each version's payload. APPEND-ONLY: keyed on the
--                       version's own minted id, so one key is one set of
--                       bytes, and an UPDATE is refused by the trigger below
--                       rather than merely avoided by the client. A payload
--                       a Drift cites has to stay what it was.
--
-- Why records are compared by `fp` and not by time
-- ------------------------------------------------
-- Two machines can each hold a version of one artifact that the other has
-- not seen. Under newest-wins, the later push replaces the earlier row and
-- the earlier machine's version is gone from the cloud. So each row carries
-- `fp`, a fingerprint of what it knows, and a client sends its copy while
-- its fingerprint differs from the cloud's; the pull merges by version id.
-- The machine that is ahead keeps sending until the cloud agrees with it.
-- `updated_at` is the time a row was SENT, which is what a pull's cursor
-- needs, and barry_keep_newest still arbitrates within that.
-- ===========================================================================

create table if not exists artifacts (
  id           text        primary key,          -- minted, never changes
  kind         text        not null,             -- circuit | drift
  schema       text,
  subject      jsonb       not null default '{}'::jsonb,
  subject_key  text,
  name         text,                              -- automatic, from metadata
  nickname     text,                              -- the user's own
  nickname_at  timestamptz,                       -- which nickname is newer
  version      integer,
  -- [{v, id, digest, at, by, machine, app_version, commit, params,
  --   params_hash, inputs, note, n_summary, confirmed}] -- no payloads.
  versions     jsonb       not null default '[]'::jsonb,
  -- [{id, version, version_id, digest, by_id, by_version, at}]
  cited        jsonb       not null default '[]'::jsonb,
  added        jsonb,
  added_at     timestamptz,
  deleted      jsonb,
  deleted_at   timestamptz,
  fp           text,
  updated_at   timestamptz not null default now(),
  updated_by   text
);
create index if not exists artifacts_kind_idx on artifacts (kind);
create index if not exists artifacts_subject_idx on artifacts (subject_key);
create index if not exists artifacts_updated_idx on artifacts (updated_at);

create table if not exists artifact_snapshots (
  artifact_id  text        not null references artifacts(id) on delete cascade,
  version_id   text        not null,
  v            integer,
  -- sha1 of the canonical payload, first 12 hex -- the version's own digest.
  -- Checked on arrival against both the payload and the version row, so a
  -- truncated or altered transfer is reported and never filed.
  digest       text,
  payload      jsonb       not null,
  machine      text,
  updated_at   timestamptz not null default now(),
  primary key (artifact_id, version_id)
);
create index if not exists artifact_snapshots_updated_idx
  on artifact_snapshots (updated_at);

alter table artifacts enable row level security;
alter table artifact_snapshots enable row level security;
revoke all on artifacts from anon;
revoke all on artifact_snapshots from anon;

drop trigger if exists artifacts_keep_newest on artifacts;
create trigger artifacts_keep_newest
  before insert or update on artifacts
  for each row execute function barry_keep_newest();

-- A payload is written once. An upsert that finds the key already there
-- keeps what is there, whatever it was sent.
create or replace function barry_add_only()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'UPDATE' then
    return old;
  end if;
  return new;
end;
$$;

drop trigger if exists artifact_snapshots_add_only on artifact_snapshots;
create trigger artifact_snapshots_add_only
  before update on artifact_snapshots
  for each row execute function barry_add_only();

comment on table artifacts is
  'Jarvis Artifacts: versioned things a stage makes and a later stage reads '
  '(Circuit, Drift). Metadata only; payloads are in artifact_snapshots.';
comment on table artifact_snapshots is
  'Each artifact version''s payload. Append-only by trigger: a version a '
  'Drift cites must stay what it was.';

-- ---------------------------------------------------------------------------
-- The watermark view (migration 17), with the two new tables. Without these
-- two lines a pull that trusts the view would skip them for ever.
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
  union all select 'artifact_snapshots', max(updated_at) from public.artifact_snapshots;

grant select on public.barry_watermarks to anon, authenticated, service_role;
