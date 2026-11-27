# time-routes-after-startup-settles

_Timing a backend route right after importing backend.app reads 10-20x slow; the start-up threads (warm, bank mirror, prewarm) contend for about 30-40 s._

When you time a route or a store call in-process (`from backend import app`,
then `app.test_client()` or `A.CLOUD.item_states`), wait about 40 s after
the import before timing anything.

**Why:** on 2026-10-22, per-kind `item_states` read bank 2042 ms, braces
1127 ms and artifacts 851 ms straight after the import. Forty seconds later
the same calls took 34, 22 and 53 ms. The import starts the syncitems warm
thread (after 12 s), the bank mirror writes and the prewarm, and they hold
the GIL and the disk. cProfile on Python 3.14 also records those other
threads, so a profile taken then blames code that is not in the request at
all (bankmirror._safe_write turned up in a cloud/items profile).

**How to apply:** `time.sleep(40)` after the import, then time each call
twice and take the second. Timing the live Jarvis over HTTP while a harness
batch runs is contended the same way, so quote numbers from a quiet run
only. See [measure-dont-guess](measure-dont-guess.md) and `virtual-time-cannot-time` (a note not copied here).
