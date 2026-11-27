# measure-dont-guess

_On BARRY GUI, diagnose UI complaints with a purpose-built browser harness rather than reading CSS or judging by eye._

Every vague UI report on this project ("it's cramped", "the buttons don't
work", "it kicks me out of the box") has turned out to have a specific,
measurable cause that reading the code did not reveal and a screenshot did
not either.

**Why:** "none of the buttons work" was `.strata-rail` at z-index 6 lying
over the left 122px of the bar — `elementFromPoint` said so in one line,
after CSS review had found nothing. "It kicks me out of the text box" was a
re-render destroying the focused input, invisible unless you type one
character at a time and check `document.activeElement` after each.

**How to apply:** write a page in `web/_dev/` that drives the real app in an
iframe and asserts on measured facts — `elementFromPoint` for "can this be
clicked", `scrollWidth > clientWidth` for "is this cut off",
`document.activeElement` after each keystroke for focus, and
`offsetParent !== null` for "is this actually on screen" (a folded-away
button is still in the DOM, and `querySelectorAll` finds it).

Run it headless with Edge, which is installed:

    msedge.exe --headless=new --disable-gpu --no-sandbox \
      --user-data-dir=<a fresh dir> \
      --virtual-time-budget=240000 \
      --dump-dom "http://127.0.0.1:<port>/_dev/<page>.html"

`--virtual-time-budget` is what lets a harness with `sleep()` in it finish;
a fresh `--user-data-dir` each run avoids a stale profile. Add
`--window-size=W,H --hide-scrollbars --screenshot=out.png` to look at it.

Two traps that cost real time here:

- **Windows lets several processes bind the same port**, and `pkill -f` does
  not match a `python -c "..."` command line. So a restart appears to work
  while the *old* server keeps answering and you test code you did not
  write. Kill by PID from `netstat -ano | grep LISTENING` and assert the
  listener count is 1 before believing a result.
- A harness that only passes on a machine it has not been run on before is
  not a check. Make setup self-healing — unarchive, close, re-blank whatever
  a previous interrupted run left behind.

State plainly when a failure is the harness's own bug. See
[never-truncate-text](never-truncate-text.md).
