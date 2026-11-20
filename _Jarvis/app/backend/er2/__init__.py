"""EXTRACTION ROOM 2.0 (asked 2026-11-18): can anything in the dentate spikes
tell PTEN from control, low from high knockout, IED+ from IED-, or guess the
knockout -- and if so, what?

  amber.py    freezes the inputs ("set in amber"): every Halo-set event with
              everything measured about it, each recording's winning
              classifier's DS1 / DS2 / DS3 call, and per-recording tables.
              One versioned bundle; nothing downstream re-classifies.
  engine.py   targets, input views, the models, mouse-level testing (one
              control and one PTEN mouse out for PTEN against control; one
              mouse out for everything else), scores, the leaderboard.
  nets.py     the two set networks (deep sets, attention pooling), in numpy so
              they run the same here and on the VACC without a GPU stack.
  explain.py  opening a model: permutation importance, Shapley values, drop
              one family, attention weights, and the MOST IMPORTANT list that
              consolidates them.
  run.py      one task (target x view x model) as the VACC runs it.

Every label belongs to a mouse; a model sees a mouse's whole cloud of events
and makes one call for the mouse. A held-out mouse's events are never seen in
training. With 16 mice, a score is only as good as 16 calls -- the pages say so.
"""
