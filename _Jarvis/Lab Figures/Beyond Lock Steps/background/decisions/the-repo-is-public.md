# the-repo-is-public

_jbarry4/jeremystats on GitHub is PUBLIC (checked 2026-11-05 via the unauthenticated API); secrets travel through the Supabase key, never git._

GitHub's API answered `private: false, visibility: public` for jbarry4/jeremystats on 2026-11-05, and raw.githubusercontent.com serves its files without sign-in. Anything committed is world-readable, including Colony Management/ and the sync records under it.

**Why:** a PIN-sealed secret in git is crackable offline (100k PINs); the Supabase service key is per machine and gitignored (GUI_logs/.cloud.json), so the private `results` bucket is the gated channel.
**How to apply:** shared secrets go to Supabase storage (see `softmouse-list-is-a-json-call` (a note not copied here)), machine secrets to %LOCALAPPDATA%\Jarvis; gitignore any plaintext credential file the user drops in the tree (root .gitignore has `user_pass.txt`). Related: `vos-import-decisions` (a note not copied here) (the sheet is link-readable too).
