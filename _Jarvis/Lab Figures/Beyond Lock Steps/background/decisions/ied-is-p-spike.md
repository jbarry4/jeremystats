# ied-is-p-spike

_Since 2026-11-05 every user-visible "IED" says "P-spike"; DS blue (--call-ds), P-spikes red (--call-p); stored id stays 'ied'._

The user (2026-11-05): "anywhere where there was a reference to IED change it to p-spike. General color code. P-spikes red; DS blue."

- Write "P-spike" / "P-spikes" ("a P-spike") in every string a person sees. Never upper-case a stored call to show it: rootcanal.js has `callWord()`, rcdeep.py has `_word()`.
- The stored id stays `ied` (event types, calls, keys, groups) so old sets and sync keep working. The Bank's summaries show old "IED" type names as "P-spike" on a copy only. store.get_presets renames the built-in "IED" filter on the way out.
- Kept on purpose: the workbook/mouse-book subgroup values IED+/IED- (matched as typed), folder paths like IED/03_IED_Detection, and code comments.
- Colours: `--call-ds` (#5aa9ff dark themes, #1f6feb light themes) and `--call-p` (var(--err)). `--o-incisor`/`--o-doppler` point at them. figkit COLOUR ied is #D62728.
- The rule is in GUI-CONSTITUTION.md next to the detector colours.

**Why:** the lab renamed the event; the user wants one vocabulary and one colour code app-wide.
**How to apply:** any new UI text, legend or figure that shows the DS / P-spike calls. Related: [the-confluence-decisions](the-confluence-decisions.md).
