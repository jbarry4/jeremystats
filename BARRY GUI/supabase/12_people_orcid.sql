-- ===========================================================================
-- BARRY GUI -- migration 12: the last roster field
--
-- Run after 01-11. Idempotent.
--
-- `role`, `initials` and `note` already have columns; `orcid` does not, so
-- it was the one detail with nowhere to go even once the push started
-- sending them. Added for completeness rather than because anybody has
-- filled one in yet -- an ORCID is how a person is cited, and a lab that
-- publishes will want it beside the name it publishes under.
-- ===========================================================================
alter table people add column if not exists orcid text;

comment on column people.orcid is
  'ORCID identifier, if they have one. Typed by hand like the role and the '
  'initials -- none of which travelled at all until the push started '
  'sending the hand-written half of a roster entry.';
