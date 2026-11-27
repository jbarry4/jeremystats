# scripts-must-wire-the-profile

_A bare storemod.Store in a script stamps records with the git identity, not the user's profile; wire Profile and Device onto it before writing._

`Store.provenance()` uses `STORE.profile` and `STORE.device`, which only
`backend/app.py` attaches. A script that builds `storemod.Store(...)` and
calls `upsert_session` writes `user: (email removed)`,
`machine: DESKTOP-4H65AI7` and no email -- the git identity and the
hostname -- where the app writes `Shahriar Tafti` / `Bluebarry` /
`(email removed)`. It happened on 2026-10-13 with 14 quality flags. They
were rewritten with the right identity.

**Why:** it gives no error. The record looks right until someone asks who
made the call, and the curation history then has the decision under a name
nobody here uses.

**How to apply:** in any script that writes records, before the first write:

    PROFILE = profilemod.Profile(LOGS, STORE); STORE.profile = PROFILE
    DEVICE = devicemod.Device(LOGS, STORE); STORE.device = DEVICE
    PROFILE.device = DEVICE

Print `STORE.provenance()` before you apply. Don't call `DEVICE.adopt`,
because that is the launcher's job. Editing a line in `GUI_logs/activity/` afterwards
is refused as audit tampering, so get the identity right before the write.
Related: [machine-has-two-names](machine-has-two-names.md), `harnesses-must-restore-not-clear` (a note not copied here).
