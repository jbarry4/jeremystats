-- ===========================================================================
-- BARRY GUI -- Supabase schema
--
-- Run this first, in the Supabase SQL editor, then 02_rls.sql, then
-- 03_storage.sql. It is safe to run more than once.
--
-- What this is for
-- ----------------
-- Everything BARRY remembers used to live as JSON files in git, split per
-- machine so two people could never write the same file. That works, and it
-- is why nothing was ever lost -- but it makes the lab's own data awkward to
-- query, and every answer has to be recomputed by walking a few hundred
-- files. Postgres is the right shape for it.
--
-- The files do not go away. BARRY still writes locally first, so it keeps
-- working on a rig with no network and on a drive that is not mounted, and
-- syncs in the background. This is the shared source of truth; the files are
-- the offline buffer.
--
-- The one rule that matters
-- ------------------------
-- A machine that has been offline for a week will push edits that are older
-- than what is already here. Every table therefore carries `updated_at`, and
-- a trigger drops any write that is older than the row it would replace. Not
-- "usually fine" -- enforced, in the database, so no client can get it wrong.
--
-- Things that are sets get real rows rather than a JSON array: the paths a
-- recording has been seen at, the sightings, one row per curated event, one
-- row per channel of a layer sheet. That is what lets two people curate the
-- same set at once and both keep their work, which a jsonb blob cannot do.
-- ===========================================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Last-writer-wins, decided by the clock the writer stamped, not by arrival
-- order. A push from a laptop that was offline since Tuesday must not undo
-- Wednesday's work just because it arrived on Thursday.
-- ---------------------------------------------------------------------------
create or replace function barry_keep_newest()
returns trigger
language plpgsql
as $$
begin
  if new.updated_at is null then
    new.updated_at := now();
  end if;
  if tg_op = 'UPDATE' and old.updated_at is not null
     and new.updated_at <= old.updated_at then
    -- Older than what is already here: keep what is here.
    return old;
  end if;
  return new;
end;
$$;

-- Applied to every table below by the loop at the bottom of this file.

-- ===========================================================================
-- Machines -- who has been writing
-- ===========================================================================
create table if not exists machines (
  id          text primary key,          -- "desktop-4h65ai7-d565"
  hostname    text,
  os          text,
  git_user    text,
  first_seen  timestamptz not null default now(),
  last_seen   timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ===========================================================================
-- Recordings
--
-- `gid` is the permanent id BARRY mints on first contact and never
-- recomputes. Everything else hangs off it. `key` is derived from mouse +
-- session + header start and is how a recording is *recognised* across
-- machines -- it can change if a header is re-read, which is exactly why it
-- is not the primary key.
-- ===========================================================================
create table if not exists sessions (
  gid             text primary key,
  key             text,
  loose_key       text,
  mouse           integer,
  session         integer,
  label           text,
  project         text,
  project_source  text,
  cohort          text,
  grp             text,                  -- the folder group, when it differs
  started_at      timestamptz,           -- the recording's own start time
  condition       text,                  -- base / cno, from the workbook
  note            text,
  bad_channels    integer[] not null default '{}',
  bad_channels_note text,
  n_channels      integer,
  fs              double precision,
  duration_s      double precision,
  has_video       boolean not null default false,
  converted       boolean not null default false,
  first_seen_by   text,
  retired         boolean not null default false,
  merged_into     text,                  -- set on a record folded into another
  split_from      text,
  -- Things that are genuinely one blob: the per-recording event colour map,
  -- committed spike sets, saved bookmarks. Small, and always read whole.
  event_classes   jsonb not null default '{}'::jsonb,
  spike_labels    jsonb not null default '{}'::jsonb,
  bookmarks       jsonb not null default '[]'::jsonb,
  created_at      timestamptz not null default now(),
  created_by      text,
  updated_at      timestamptz not null default now(),
  updated_by      text
);
create index if not exists sessions_key_idx      on sessions (key);
create index if not exists sessions_loose_idx    on sessions (loose_key);
create index if not exists sessions_project_idx  on sessions (project);
create index if not exists sessions_mouse_idx    on sessions (mouse, session);
create index if not exists sessions_updated_idx  on sessions (updated_at);

-- Where a recording has been seen. One row per machine per path, because
-- every machine legitimately knows a different mount and none is wrong.
create table if not exists session_paths (
  gid         text not null references sessions(gid) on delete cascade,
  path        text not null,
  machine     text,
  deleted_at  timestamptz,               -- soft, so "forget this path" syncs
  updated_at  timestamptz not null default now(),
  primary key (gid, path)
);
create index if not exists session_paths_updated_idx on session_paths (updated_at);

-- A sighting: this machine laid eyes on this recording, at this path, then.
-- Distinct from "BARRY remembers it", which is the whole point of the faint
-- rows in the Sessions view.
create table if not exists session_sightings (
  gid         text not null references sessions(gid) on delete cascade,
  machine     text not null,
  seen_at     timestamptz not null default now(),
  path        text,
  scan_id     text,
  root        text,
  updated_at  timestamptz not null default now(),
  primary key (gid, machine)
);
create index if not exists session_sightings_updated_idx
  on session_sightings (updated_at);

-- ===========================================================================
-- Mice -- what is true about the animal rather than the recording
--
-- Attributes are free-form on purpose. A fixed set of columns is a guess
-- about what the lab will want to record and it is wrong within a month;
-- someone always needs "implant date" or "virus batch". jsonb here, and the
-- view builds its columns from what has actually been filled in.
-- ===========================================================================
create table if not exists mice (
  project     text not null,
  mouse       integer not null,
  attrs       jsonb not null default '{}'::jsonb,
  note        text,
  created_at  timestamptz not null default now(),
  created_by  text,
  updated_at  timestamptz not null default now(),
  updated_by  text,
  primary key (project, mouse)
);
create index if not exists mice_updated_idx on mice (updated_at);

-- ===========================================================================
-- The event bank -- detected events, and whether anyone has looked at them
-- ===========================================================================
create table if not exists bank_entries (
  id              text primary key,
  gid             text references sessions(gid) on delete set null,
  project         text,
  mouse           integer,
  session         integer,
  session_key     text,
  session_label   text,
  session_path    text,
  recording_start timestamptz,
  duration_s      double precision,
  type            text,                  -- ds, ied, spike, ...
  type_name       text,
  name            text,
  note            text,
  units           text,
  n               integer not null default 0,
  -- A detector saying "there is something at 315.275 s" and a person saying
  -- "that is a dentate spike" are different claims. An import is unspecified
  -- until somebody has been through it.
  specified       boolean not null default false,
  curation_label  text,
  source          jsonb not null default '{}'::jsonb,
  added_by        text,
  added_at        timestamptz,
  added_machine   text,
  history         jsonb not null default '[]'::jsonb,
  -- The times themselves. Read whole, never queried into, and 11k of them is
  -- about 200 kB of jsonb -- a row per event would be 11k rows for something
  -- nobody filters on.
  events          jsonb not null default '[]'::jsonb,
  deleted_at      timestamptz,
  updated_at      timestamptz not null default now(),
  updated_by      text
);
create index if not exists bank_gid_idx     on bank_entries (gid);
create index if not exists bank_type_idx    on bank_entries (type);
create index if not exists bank_updated_idx on bank_entries (updated_at);

-- ===========================================================================
-- Curation -- one row per decision, so two people can share the work
-- ===========================================================================
create table if not exists curation_sets (
  id            text primary key,        -- <gid>__<kind>
  gid           text not null references sessions(gid) on delete cascade,
  kind          text not null,           -- ds | ied
  name          text,
  session_label text,
  source        jsonb not null default '{}'::jsonb,
  imports       jsonb not null default '[]'::jsonb,
  -- Copied in, so a set labelled last year still means what it meant if the
  -- vocabulary grows.
  vocabulary    jsonb not null default '[]'::jsonb,
  deleted_at    timestamptz,
  created_at    timestamptz not null default now(),
  created_by    text,
  updated_at    timestamptz not null default now(),
  updated_by    text,
  unique (gid, kind)
);

create table if not exists curation_events (
  set_id      text not null references curation_sets(id) on delete cascade,
  event_id    text not null,
  start_s     double precision not null,
  end_s       double precision,
  channel     integer,
  amplitude   double precision,
  label       text not null default 'unspecified',
  decided_by  text,
  decided_at  timestamptz,
  updated_at  timestamptz not null default now(),
  primary key (set_id, event_id)
);
create index if not exists curation_events_set_idx   on curation_events (set_id);
create index if not exists curation_events_label_idx on curation_events (set_id, label);
create index if not exists curation_events_updated_idx
  on curation_events (updated_at);

-- ===========================================================================
-- StrataScope -- which anatomical layer each channel sits in
--
-- Keyed by CSC number, not row index: a row index shifts the moment someone
-- toggles even-only or a channel file goes missing, and CSC14 is always
-- CSC14.
-- ===========================================================================
create table if not exists layer_sheets (
  gid           text primary key references sessions(gid) on delete cascade,
  session_label text,
  channels      integer[] not null default '{}',
  regions       jsonb not null default '[]'::jsonb,
  deleted_at    timestamptz,
  created_at    timestamptz not null default now(),
  created_by    text,
  updated_at    timestamptz not null default now(),
  updated_by    text
);

create table if not exists layer_labels (
  gid         text not null references layer_sheets(gid) on delete cascade,
  channel     integer not null,
  region      text,                      -- null means "cleared"
  set_by      text,
  updated_at  timestamptz not null default now(),
  primary key (gid, channel)
);
create index if not exists layer_labels_updated_idx on layer_labels (updated_at);

-- ===========================================================================
-- Results, storyboards, runs
-- ===========================================================================
create table if not exists results (
  id           text primary key,         -- hash of the repo-relative path
  rel_path     text not null unique,     -- portable: never an absolute path
  title        text,
  kind         text,
  type         text,
  bytes        bigint,
  gid          text references sessions(gid) on delete set null,
  session_key  text,
  session_label text,
  run_id       text,
  script       text,
  machine      text,
  author       text,
  made_at      timestamptz,
  -- The directory it actually sits in under Results/. Filing something in
  -- the GUI moves the file, so this is the folder you would see if you
  -- opened Results/ in Explorer -- one idea, not a label beside a path that
  -- disagrees with it.
  folder       text,
  tags         text[] not null default '{}',
  notes        text,
  starred      boolean not null default false,
  -- Where the bytes are in the storage bucket, once uploaded.
  storage_path text,
  storage_at   timestamptz,
  deleted_at   timestamptz,
  updated_at   timestamptz not null default now(),
  updated_by   text
);
create index if not exists results_folder_idx  on results (folder);
create index if not exists results_gid_idx     on results (gid);
create index if not exists results_updated_idx on results (updated_at);

create table if not exists storyboards (
  id          text primary key,
  title       text,
  slides      jsonb not null default '[]'::jsonb,
  n_slides    integer not null default 0,
  deleted_at  timestamptz,
  created_at  timestamptz not null default now(),
  created_by  text,
  updated_at  timestamptz not null default now(),
  updated_by  text
);
create index if not exists storyboards_updated_idx on storyboards (updated_at);

create table if not exists runs (
  id          text primary key,
  script      text,
  label       text,
  lang        text,
  status      text,
  gid         text references sessions(gid) on delete set null,
  session_key text,
  session_label text,
  parameters  jsonb not null default '{}'::jsonb,
  outputs     jsonb not null default '[]'::jsonb,
  started_at  timestamptz,
  ended_at    timestamptz,
  duration_s  double precision,
  machine     text,
  git_user    text,
  updated_at  timestamptz not null default now()
);
create index if not exists runs_started_idx on runs (started_at desc);
create index if not exists runs_gid_idx     on runs (gid);
create index if not exists runs_updated_idx on runs (updated_at);

-- ===========================================================================
-- Append-only logs
--
-- These are never edited, only added to, so they need no merge rule -- the
-- primary key is a uuid the writer minted and a second insert of the same row
-- is a no-op.
-- ===========================================================================
create table if not exists activity (
  id          text primary key,
  at          timestamptz not null,
  action      text not null,
  detail      jsonb not null default '{}'::jsonb,
  gid         text,
  session_key text,
  view        text,
  git_user    text,
  machine     text,
  updated_at  timestamptz not null default now()
);
create index if not exists activity_at_idx     on activity (at desc);
create index if not exists activity_action_idx on activity (action);

create table if not exists errors (
  id          text primary key,
  at          timestamptz not null,
  where_      text,
  message     text,
  detail      text,
  context     jsonb not null default '{}'::jsonb,
  machine     text,
  git_user    text,
  updated_at  timestamptz not null default now()
);
create index if not exists errors_at_idx on errors (at desc);

-- Triage is an edit, so it is separate from the append-only log above and
-- keyed on the grouping signature: one mark clears every past repeat.
create table if not exists error_marks (
  signature   text primary key,
  resolved    boolean not null default true,
  note        text,
  marked_by   text,
  machine     text,
  updated_at  timestamptz not null default now()
);

-- ===========================================================================
-- Presets and per-machine preferences
-- ===========================================================================
create table if not exists presets (
  kind        text not null,             -- filters | imports | layouts
  id          text not null,
  name        text,
  payload     jsonb not null default '{}'::jsonb,
  builtin     boolean not null default false,
  deleted_at  timestamptz,
  updated_at  timestamptz not null default now(),
  updated_by  text,
  primary key (kind, id)
);

-- Theme, pane sizes and "where was I" describe the screen in front of you,
-- not the project -- so they stay per machine and are never merged. Shared
-- preferences (favourites, collections) live in `shared`.
create table if not exists prefs (
  machine     text primary key,
  local       jsonb not null default '{}'::jsonb,
  shared      jsonb not null default '{}'::jsonb,
  updated_at  timestamptz not null default now()
);

-- ===========================================================================
-- The newest-wins trigger, on everything
-- ===========================================================================
do $$
declare
  t text;
begin
  foreach t in array array[
    'machines', 'sessions', 'session_paths', 'session_sightings', 'mice',
    'bank_entries', 'curation_sets', 'curation_events', 'layer_sheets',
    'layer_labels', 'results', 'storyboards', 'runs', 'activity', 'errors',
    'error_marks', 'presets', 'prefs'
  ]
  loop
    execute format(
      'drop trigger if exists %I on %I', t || '_keep_newest', t);
    execute format(
      'create trigger %I before insert or update on %I
       for each row execute function barry_keep_newest()',
      t || '_keep_newest', t);
  end loop;
end;
$$;

-- ===========================================================================
-- A couple of views, because these are the questions people actually ask
-- ===========================================================================
create or replace view v_session_overview as
select
  s.gid, s.label, s.project, s.cohort, s.mouse, s.session,
  s.started_at::date as recorded_on, s.condition,
  s.n_channels, s.duration_s,
  cardinality(s.bad_channels)                       as n_bad,
  s.bad_channels,
  (select count(*) from session_paths p
    where p.gid = s.gid and p.deleted_at is null)   as n_paths,
  (select count(*) from session_sightings v
    where v.gid = s.gid)                            as n_machines,
  (select max(v.seen_at) from session_sightings v
    where v.gid = s.gid)                            as last_seen,
  (select count(*) from bank_entries b
    where b.gid = s.gid and b.deleted_at is null)   as n_banked,
  (select count(*) from layer_labels l
    where l.gid = s.gid and l.region is not null)   as n_layers,
  (select count(*) from results r
    where r.gid = s.gid and r.deleted_at is null)   as n_results,
  m.attrs                                           as mouse_attrs
from sessions s
left join mice m on m.project = s.project and m.mouse = s.mouse
where not s.retired;

create or replace view v_curation_progress as
select
  c.id, c.gid, c.kind, c.name, c.session_label,
  count(*)                                                as total,
  count(*) filter (where e.label <> 'unspecified')        as specified,
  count(*) filter (where e.label = 'unspecified')         as remaining,
  round(100.0 * count(*) filter (where e.label <> 'unspecified')
        / greatest(count(*), 1), 1)                       as percent,
  max(e.decided_at)                                       as last_decision
from curation_sets c
left join curation_events e on e.set_id = c.id
where c.deleted_at is null
group by c.id, c.gid, c.kind, c.name, c.session_label;
