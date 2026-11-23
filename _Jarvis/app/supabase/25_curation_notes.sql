-- ===========================================================================
-- 25 -- notes on curated events (2026-11-20)
--
-- Run once, in the SQL editor of the lab's project, after 01-24. Safe to run
-- again.
--
-- WHY. Anything that can be flagged in Panning, Checkup or Spotter can now
-- carry a note ("two spikes on top of each other, kept the second"), and
-- the note has to reach everyone else's copy of the set. Until this runs,
-- Jarvis leaves the three columns out of what it sends, notes stay on the
-- computer that wrote them, and the Sync panel names this file.
--
-- WHAT. Three columns on curation_events -- the note, who wrote it, when --
-- and a merge in place of last-writer-wins for that one table.
--
-- The row used to be one register: whichever copy had the newer
-- `updated_at` won, label and all. A note is written at a different moment
-- from the decision beside it, often by a different person, so a note added
-- to a copy that had not yet heard about a colleague's newer call would have
-- carried the old call back over it. So the row is now three registers, each
-- with its own clock:
--
--   the decision  label, decided_by, decided_at   -- newer decided_at wins
--   the note      note, note_by, note_at          -- newer note_at wins
--   the rest      start_s, end_s, channel, ...    -- newer updated_at wins,
--                                                    as before
--
-- A decision with no time (never decided) still yields to the row as a
-- whole, exactly as before, so nothing that synced correctly yesterday
-- syncs differently today. `_zz_arrival` (migration 24) still runs after
-- this and still stamps `synced_at` only when something actually changed.
-- ===========================================================================

alter table public.curation_events add column if not exists note    text;
alter table public.curation_events add column if not exists note_by text;
alter table public.curation_events add column if not exists note_at timestamptz;

create or replace function barry_curation_event_merge()
returns trigger
language plpgsql
as $$
declare
  newer_row boolean;
begin
  if new.updated_at is null then
    new.updated_at := now();
  end if;
  if tg_op <> 'UPDATE' then
    return new;
  end if;
  newer_row := old.updated_at is null or new.updated_at > old.updated_at;

  -- The decision: by its own time when either side has one, else by the row.
  if old.decided_at is not null or new.decided_at is not null then
    if coalesce(old.decided_at, '-infinity'::timestamptz)
         >= coalesce(new.decided_at, '-infinity'::timestamptz)
       and not (old.decided_at is not distinct from new.decided_at
                and newer_row) then
      new.label      := old.label;
      new.decided_by := old.decided_by;
      new.decided_at := old.decided_at;
    end if;
  elsif not newer_row then
    new.label      := old.label;
    new.decided_by := old.decided_by;
    new.decided_at := old.decided_at;
  end if;

  -- The note: newer note_at wins; a row that says nothing keeps what is here.
  if coalesce(old.note_at, '-infinity'::timestamptz)
       >= coalesce(new.note_at, '-infinity'::timestamptz) then
    new.note    := old.note;
    new.note_by := old.note_by;
    new.note_at := old.note_at;
  end if;

  -- Everything else, as barry_keep_newest always did.
  if not newer_row then
    new.start_s    := old.start_s;
    new.end_s      := old.end_s;
    new.channel    := old.channel;
    new.amplitude  := old.amplitude;
    new.updated_at := old.updated_at;
  end if;
  return new;
end;
$$;

-- In place of curation_events_keep_newest, under the same name: triggers run
-- in name order, and this one has to run before `_zz_arrival`.
drop trigger if exists curation_events_keep_newest on public.curation_events;
create trigger curation_events_keep_newest
  before update or insert on public.curation_events
  for each row execute function barry_curation_event_merge();
