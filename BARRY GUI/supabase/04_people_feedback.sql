-- ===========================================================================
-- BARRY GUI -- migration 04: people, feedback, and the curation workbench
--
-- Run this after 01_schema.sql, 02_rls.sql and 03_storage.sql, on a project
-- that already has them. It is idempotent: every statement is `if not
-- exists` or `add column if not exists`, so running it twice is harmless
-- and running it on a fresh project after 01-03 works too.
--
-- Three things were local-only and shouldn't have been:
--
--   feedback   A report filed on the rig never reached the desktop, and a
--              triage decision made on the desktop never reached the rig.
--              Two people were each looking at their own half of the list
--              and neither could tell.
--
--   people     The roster is compiled from names already stamped on the
--              data, which works on one machine and only sees that
--              machine's shards until a pull. A table lets somebody added
--              on one computer be pickable on another immediately.
--
--   the bench  `open`, `assignee` and `opened_at` are how the curation view
--              says whose work a set is. Without columns for them, "Rain
--              has m33 s8 open" is a fact that stops at the machine she is
--              sitting at.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- People
--
-- Keyed by the name as typed, because that is what every other record
-- carries -- `curation_events.decided_by` is a name, not an id, and a
-- roster keyed on something else could not be joined to it. `email` is the
-- thing to deduplicate on later if it ever matters.
-- ---------------------------------------------------------------------------
create table if not exists people (
  name        text primary key,
  email       text,
  role        text,
  initials    text,
  note        text,
  -- Whether this is somebody who can be asked about a decision, or a record
  -- of where one came from. "snapshot import" is the latter and must never
  -- be offered as the owner of a session.
  is_person   boolean not null default true,
  -- Where the name was seen, so the picker can say "48 decisions, 3 banked
  -- versions" rather than presenting two similar names with nothing to tell
  -- them apart.
  seen        jsonb not null default '{}'::jsonb,
  added_by    text,
  first_seen  timestamptz not null default now(),
  last_seen   timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Feedback
--
-- `id` is the id BARRY already mints per report, so the local file and the
-- row are the same record. Screenshots stay in storage (03_storage.sql) and
-- are referenced by name -- a 4 MB PNG does not belong in a jsonb column.
-- ---------------------------------------------------------------------------
create table if not exists feedback (
  id          text primary key,
  kind        text not null,             -- bug | feature | improvement
  state       text not null default 'open',  -- open|planned|done|declined
  title       text,
  body        text,
  -- What they want instead, kept apart from the description of what
  -- happened: they are different questions and the form asks both.
  wants       text,
  -- Where the person was when they filed it, which is most of the value.
  context     jsonb not null default '{}'::jsonb,
  view        text,
  session_label text,
  gid         text,
  shots       jsonb not null default '[]'::jsonb,
  votes       jsonb not null default '[]'::jsonb,
  -- Triage. Who changed the state and when, so two people are not silently
  -- overwriting each other's decisions.
  state_by    text,
  state_at    timestamptz,
  machine     text,
  deleted_at  timestamptz,
  created_at  timestamptz not null default now(),
  created_by  text,
  updated_at  timestamptz not null default now(),
  updated_by  text
);
create index if not exists feedback_state_idx on feedback (state);
create index if not exists feedback_updated_idx on feedback (updated_at);

-- A reply on a report, so a conversation about it is not a single body
-- field two people take turns overwriting.
create table if not exists feedback_notes (
  id          text primary key,
  feedback_id text not null references feedback(id) on delete cascade,
  body        text not null,
  note_by     text,
  at          timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists feedback_notes_parent_idx
  on feedback_notes (feedback_id);

-- ---------------------------------------------------------------------------
-- The curation workbench
--
-- Added to the existing table rather than a new one: these are properties
-- of a set, not records of their own.
-- ---------------------------------------------------------------------------
alter table curation_sets add column if not exists assignee   text;
alter table curation_sets add column if not exists is_open    boolean not null default false;
alter table curation_sets add column if not exists opened_at  timestamptz;
alter table curation_sets add column if not exists opened_by  text;
alter table curation_sets add column if not exists closed_at  timestamptz;
alter table curation_sets add column if not exists archived   boolean not null default false;
alter table curation_sets add column if not exists archived_at timestamptz;
alter table curation_sets add column if not exists archived_by text;

-- `open` is a reserved word in SQL, which is why the column is `is_open`.
-- The invariant the interface depends on, stated where it cannot be
-- forgotten: a set that is both archived and open belongs to neither the
-- bench nor the shelf, and simply disappears from the view.
alter table curation_sets drop constraint if exists curation_sets_not_both;
alter table curation_sets add constraint curation_sets_not_both
  check (not (is_open and archived));

-- Per-candidate review rows: "two people agreed" is worth more than one
-- person's call, and it cannot be said without somewhere to record the
-- second person having looked.
create table if not exists curation_reviews (
  set_id      text not null references curation_sets(id) on delete cascade,
  event_id    text not null,
  reviewer    text not null,
  label       text not null,
  at          timestamptz,
  updated_at  timestamptz not null default now(),
  primary key (set_id, event_id, reviewer)
);
create index if not exists curation_reviews_set_idx
  on curation_reviews (set_id);

-- ---------------------------------------------------------------------------
-- Row level security, matching 02_rls.sql: on, with no `anon` policies, so
-- only the secret key can read or write. See the note at the top of that
-- file before changing this.
-- ---------------------------------------------------------------------------
alter table people            enable row level security;
alter table feedback          enable row level security;
alter table feedback_notes    enable row level security;
alter table curation_reviews  enable row level security;

-- ---------------------------------------------------------------------------
-- The newest-wins trigger that 01_schema.sql applies to every other table.
-- Without it these four would not get their `updated_at` maintained, and the
-- sync's "everything changed since X" query would never see a change.
-- ---------------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array[
    'people', 'feedback', 'feedback_notes', 'curation_reviews'
  ]
  loop
    execute format(
      'drop trigger if exists %I on %I', t || '_keep_newest', t);
    execute format(
      'create trigger %I before update on %I for each row '
      'execute function barry_keep_newest()', t || '_keep_newest', t);
  end loop;
end
$$;
