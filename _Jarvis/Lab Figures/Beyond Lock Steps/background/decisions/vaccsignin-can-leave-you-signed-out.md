# vaccsignin-can-leave-you-signed-out

__dev/vaccsignin.html signs the machine out and back in by netid; if the key check fails mid-suite it stays signed out (GUI_logs/.vacc.json loses netid/key_path)._

On 2026-10-08 a full `harness_run.py vacc ...` sweep failed vaccsignin.html with "a netid alone is enough -- No key on this computer works for sakhava1", and left `GUI_logs/.vacc.json` without `netid` and `key_path`. Every VACC call afterwards failed with "No VACC netid set." Re-run alone a minute later it passed 32/32 and restored itself. The key that works is `C:\Users\Z390\.ssh\id_ed25519`; `id_ed25519_jarvis_vacc` is refused by the cluster.

**Why:** the harness restores by signing back in through `working_key`, which tries each key with a real ssh; one transient refusal during a busy sweep and there is no fallback to the saved file.

**How to apply:** after any sweep that includes vaccsignin, check `.vacc.json` still has `netid`. If not, restore with `vacc.save_config('GUI_logs', netid='sakhava1', key_path=r'C:\Users\Z390\.ssh\id_ed25519')` and confirm with a `whoami` over `vacc._ssh`. Related: `harnesses-must-restore-not-clear` (a note not copied here).
