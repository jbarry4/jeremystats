-- ===========================================================================
-- BARRY GUI -- migration 22: the review site's open questions
--
-- Run after 01-21, in the SQL editor of the lab's project. Idempotent.
--
-- Why
-- ---
-- The Monolith goes to Travis as a review site on Vercel (project
-- dewey-monolith, assembled by tools/export_review.py). It has one list of
-- open questions that anyone with the site's password can add to, answer
-- and close. The list lives here so it survives redeploys and so Jarvis
-- can read it later.
--
-- Who can touch it
-- ----------------
-- Nobody through the public API: row level security is on and there is no
-- policy, so the anon and authenticated roles see nothing. The site's
-- function (review/site/api/questions.js) uses the service key, which lives
-- only in the Vercel project's environment, and checks every field before
-- it writes.
-- ===========================================================================

create table if not exists public.review_questions (
  id           bigint generated always as identity primary key,
  text         text        not null check (char_length(text) between 1 and 2000),
  asked_by     text        not null check (char_length(asked_by) between 1 and 80),
  about        text        check (char_length(about) <= 300),
  status       text        not null default 'open'
                           check (status in ('open', 'answered', 'closed')),
  answer       text        check (char_length(answer) <= 4000),
  answered_by  text        check (char_length(answered_by) <= 80),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists review_questions_status_idx
  on public.review_questions (status, created_at);

alter table public.review_questions enable row level security;
revoke all on public.review_questions from anon, authenticated;

comment on table public.review_questions is
  'Open questions on the DEWEY Monolith review site (dewey-monolith on '
  'Vercel). Written only by the site''s function with the service key.';

-- The questions already known when the site was made, so the list does not
-- start empty. Only into an empty table: re-running this adds nothing.
insert into public.review_questions (text, asked_by, about)
select q.text, 'Shahriar', q.about
from (values
  ('In AB only and CD only, Cue 2 − Cue 1 needs a presentation that is clean in both cues. A rat with only one such presentation on a day has no spread there, and the pooling then leaves every entry that rat is in untested; in the preview build this cut the AB-only contrast to a fraction of its entries. Keep the rule, or let such a rat in with a variance taken from its other sessions?',
   'The comparisons: Cue 2 − Cue 1, AB only'),
  ('Histology v2 keeps a left posterior probe that sat in the subiculum as its own region, Left POR-SUB, on the POR channel mapping, and leaves the right one out. Is that the right call, or should both be dropped, or both kept?',
   'Histology v2'),
  ('No correction for multiple comparisons, by design: every p is uncorrected and shown beside the count expected by chance. What should make a lead worth following up: a p threshold, a run of neighbouring frequencies, most rats the same way, agreement between measures, or something else?',
   'What came out'),
  ('The whole-pair window (cue 1 onset to cue 2 offset, 20 s) keeps a wire only if it is clean in both cues, and its Minus FP stands against 20 s rest epochs cut from FP1 and FP2. Agreed?',
   'The windows; Minus FP'),
  ('Events first: hippocampal P300-like events are found at a robust z of 4 or more, band-passed 0.5–15 Hz, 150–500 ms wide at half height, at least 500 ms apart. Are these the right defaults?',
   'The Monolith, tab 4 · Events first')
) as q(text, about)
where not exists (select 1 from public.review_questions);
