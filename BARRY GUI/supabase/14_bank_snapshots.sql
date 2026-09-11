-- ===========================================================================
-- BARRY GUI -- migration 14: the version snapshots themselves
--
-- Run after 01-13. Idempotent.
--
-- Migration 11 sent up the version history without its snapshots, and said
-- why: 110 versions are 44 kB of metadata and 0.5 MB with the snapshots, and
-- the metadata is what makes a version VISIBLE. The snapshots stayed in the
-- JSON shards, so restoring a colleague's version needed a git pull first.
-- That is the half of "a shared bank" that was still missing: you could see
-- that v7 existed, who made it and how many events it held, and you could
-- not have it.
--
-- So the snapshots travel too, in their own table.
--
-- Why this is the safe way to do it
-- ---------------------------------
-- A version's snapshot is written once and never changes. v7 of an entry is
-- what v7 was; curating further makes v8. So this table is APPEND-ONLY, and
-- that buys the strongest safety property available:
--
--   * The key is (entry_id, v). Two machines writing the same key write the
--     same bytes, so there is no last-writer, no clock to compare and no
--     merge. The whole class of "whose edit wins" bugs cannot arise here --
--     which matters, because comparing two timestamps across machines has
--     been wrong in eleven places in this codebase.
--
--   * `updated_at` is the version's own creation time, not now(). It never
--     changes, so the incremental push sends each snapshot exactly once and
--     then stops, forever.
--
--   * Nothing here replaces the JSON shard. The shard is still written and
--     still travels with the repository, so a snapshot now has two
--     independent copies instead of one. `_apply_bank_snapshots` never
--     overwrites a local snapshot with one from here: if the two disagree it
--     keeps the local copy and files an error, because a snapshot that
--     disagrees with itself is a fault to look at, not a merge to perform.
--
-- `sha256` is over the canonical JSON of the snapshot. It is what makes
-- "these two copies agree" a check rather than an assumption, and it is what
-- lets a truncated transfer be caught before somebody restores from it.
--
-- The cascade is deliberate: a snapshot whose entry has been hard-deleted is
-- unreachable anyway. Ordinary deletion in BARRY is a `deleted_at` tombstone,
-- which does not fire this.
-- ===========================================================================
create table if not exists bank_snapshots (
  entry_id   text        not null references bank_entries(id) on delete cascade,
  v          integer     not null,
  -- How many events the snapshot holds, so a row can be sized and sanity
  -- checked without parsing the payload.
  n          integer     not null default 0,
  sha256     text,
  -- [[start, label], ...] -- the same compact pairs the JSON shard holds.
  snap       jsonb       not null,
  -- Which machine made this version, for provenance. NOT part of the key:
  -- the snapshot belongs to the version, not to the computer that typed it.
  machine    text,
  -- The version's own creation time. Immutable, which is what makes the
  -- incremental push send this row once and never again.
  updated_at timestamptz not null default now(),
  primary key (entry_id, v)
);

create index if not exists bank_snapshots_entry_idx
  on bank_snapshots (entry_id);
create index if not exists bank_snapshots_updated_idx
  on bank_snapshots (updated_at);

alter table bank_snapshots enable row level security;

comment on table bank_snapshots is
  'The restorable copy of each banked version. Append-only and keyed '
  '(entry_id, v), so two machines writing the same version write the same '
  'bytes and no merge is ever needed. Does not replace the JSON shard -- '
  'together they are two independent copies of work that used to have one.';
comment on column bank_snapshots.sha256 is
  'sha256 of the canonical JSON of `snap`. Makes "both copies agree" a '
  'check rather than an assumption, and catches a truncated transfer before '
  'anybody restores from it.';
comment on column bank_snapshots.updated_at is
  'The version''s creation time, never now(). It does not change, so the '
  'incremental push sends each snapshot exactly once.';
