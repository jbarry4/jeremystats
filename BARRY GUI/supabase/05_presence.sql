-- ===========================================================================
-- BARRY GUI -- migration 05: who is curating what, right now
--
-- Run after 01-04, on a project that already has them. Idempotent: every
-- statement is `if not exists`, so running it twice is harmless.
--
-- The problem this solves is two people opening the same set and deciding
-- the same six hundred candidates twice -- and worse, deciding them
-- differently, so the merge has to pick a winner and somebody's afternoon
-- quietly loses. Nothing in the store could have prevented that: a curation
-- set knows who it is ASSIGNED to and when it was last OPENED, and neither
-- of those is the same as somebody being in it at this moment.
--
-- So this table is about the present tense, and it is the only table in the
-- schema that is allowed to be wrong in a minute's time. Every other row is
-- a record of something that happened; a presence row is a claim that
-- somebody is at their keyboard, and claims like that go stale the instant
-- a laptop lid closes. Hence `last_seen` and a time-to-live rather than an
-- explicit lock that would have to be released -- a lock you must remember
-- to give back is a lock that strands work when a machine crashes, and the
-- one thing worse than two people in a set is nobody able to get into it.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- One row per machine per set. The primary key is (gid, kind, machine) and
-- not (gid, kind, person): the same person on the rig and the desktop really
-- is two sessions, and showing them as one would hide that a rig they walked
-- away from still has the set open.
-- ---------------------------------------------------------------------------
create table if not exists curation_presence (
  gid          text not null,
  kind         text not null,
  machine      text not null,

  -- Who, as a name -- the same name curation_events.decided_by carries, so
  -- the two can be joined without a lookup.
  person       text,
  -- What the machine calls itself, for somebody who has three of them.
  device       text,

  -- When this session picked the set up, and when it last said anything.
  -- The difference between them is the whole point: `started_at` is how long
  -- they have been at it, `last_seen` is whether they still are.
  started_at   timestamptz not null default now(),
  last_seen    timestamptz not null default now(),

  -- The live feed. Cheap counters rather than a stream of events: what a
  -- colleague wants to know is "how far have they got", and three integers
  -- answer that without a row per keystroke.
  n_total      integer,
  n_decided    integer,
  n_this_visit integer,          -- decided since they picked it up
  at_index     integer,          -- which candidate they are looking at
  at_time_s    double precision, -- and where in the recording that is

  -- What they are doing, so the feed can say something better than a number:
  -- 'curating', 'reviewing', 'idle', 'banking'.
  doing        text,

  -- Set when somebody deliberately takes a set that another session is in.
  -- Kept rather than deleted so the other machine can find out it was taken
  -- and say so, instead of silently writing into a set it no longer holds.
  yielded_to   text,
  yielded_at   timestamptz,

  updated_at   timestamptz not null default now(),
  primary key (gid, kind, machine)
);

create index if not exists curation_presence_seen
  on curation_presence (last_seen desc);
create index if not exists curation_presence_set
  on curation_presence (gid, kind);
-- The sync pulls "everything changed since X" across every table.
create index if not exists curation_presence_updated
  on curation_presence (updated_at desc);

alter table curation_presence enable row level security;

-- Same policy shape as every other table in 02_rls.sql: the anon key is the
-- lab's key, and everyone holding it is a member of the lab.
do $$
begin
  if not exists (
    select 1 from pg_policies
    where tablename = 'curation_presence' and policyname = 'presence_all'
  ) then
    execute 'create policy presence_all on curation_presence '
            'for all using (true) with check (true)';
  end if;
end
$$;

-- ---------------------------------------------------------------------------
-- `updated_at` maintenance, as every other table has.
--
-- NOT barry_keep_newest here, deliberately. That trigger exists to stop an
-- older write from overwriting a newer one, which is right for a record of
-- something that happened and wrong for a heartbeat: the whole content of a
-- heartbeat is that it is more recent than the last one. Newest-wins would
-- make a machine whose clock is slightly behind unable to report itself
-- present at all.
-- ---------------------------------------------------------------------------
create or replace function barry_presence_touch()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end
$$;

drop trigger if exists curation_presence_touch on curation_presence;
create trigger curation_presence_touch
  before insert or update on curation_presence
  for each row execute function barry_presence_touch();

-- ---------------------------------------------------------------------------
-- Housekeeping.
--
-- A presence row is worthless once it is old, and nobody deletes their own:
-- the commonest way a session ends is the lid closing, which sends nothing.
-- Anything unseen for a day is a machine that is not coming back to this set.
--
-- Not scheduled here -- pg_cron is not on every project. BARRY calls it on
-- its own sync, which is enough: the readers all filter on `last_seen`
-- anyway, so a stale row that lingers is untidy rather than wrong.
-- ---------------------------------------------------------------------------
create or replace function barry_presence_sweep(older_than interval default '1 day')
returns integer language plpgsql as $$
declare
  n integer;
begin
  delete from curation_presence where last_seen < now() - older_than;
  get diagnostics n = row_count;
  return n;
end
$$;
