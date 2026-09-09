# -*- coding: utf-8 -*-
"""Run every harness in web/_dev and report the tally.

Three things this had to learn the hard way, all of them about the runner
rather than about the app.

**Report formats.** The harnesses were written over months and report in
three shapes -- a `#out` div of plain lines, a `#log` `<pre>` of
`<span class="good">ok ...`, and a couple that put the verdict in the
document title. An earlier version understood only the first and reported
"0 ok, 0 fail" for two thirds of the suite, which reads exactly like a clean
run.

**The session argument.** Fifteen harnesses take `?session=<path>` and open
it without checking, so run bare `xplore.open(null)` renders nothing and
every geometry assertion fails on an empty pane. That looked like thirteen
broken harnesses and was one missing argument: `master.html` went from five
failures and a crash to 12 ok, 0 fail the moment it got one.

**But not to all of them.** Measured both ways: `bank.html` is 47 ok / 0
fail bare and CRASHES with a session, and `strata.html` skips cleanly bare
but throws on the demo recording, which has no layer sheet. So the argument
is passed per harness, and the two that are worse for it are named below.
`check.html` (crash -> 40 ok) and `smoke.html` (55 -> 69 checks) are much
better for it; the extra failures those two then report are real findings
that a crash was hiding, not regressions.
"""
import html
import os
import re
import subprocess
import sys
import urllib.parse

# Harness output is full of typographic dashes and quotes, and a Windows
# console is cp1252 -- printing one raised UnicodeEncodeError and took the
# whole run down partway through, losing every result so far. Reconfigured
# rather than sanitised at each print, so a stray character can never end a
# sweep again.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = "http://127.0.0.1:8791"
ROOT = r"c:\Users\Z390\Desktop\jeremystats\BARRY GUI"

# The demo recording, as xplore.open() takes it: checked in, always
# reachable, and nothing driving it can touch real curation data.
SESSION = "demo:long-session"

# Harnesses measured to be WORSE with it. Both treat the parameter as
# optional and take a different path when it is present.
# A known limitation, recorded so nobody chases it: `smoke.html` gets the
# demo recording and the demo has no detected events, so its six
# event-and-marks checks cannot pass -- "the session has events to test with
# [0 events]" and the five that follow from it. Giving it a real recording
# would fix those and would also point a suite that runs preflight and writes
# marks at live data, unattended. Six explained failures are the better
# trade, and it still runs 69 checks against 55 with no session at all.
NO_SESSION = {
    # 47 ok / 0 fail bare; crashes with one.
    "bank.html",
    # Skips cleanly bare; throws on the demo, which has no layer sheet. It
    # wants a recording with StrataScope labels.
    "strata.html",
}

TAG = re.compile(r"<[^>]+>")
OK = re.compile(r"(?m)^\s*(?:ok|OK|PASS|\u2713)\b")
BAD = re.compile(r"(?m)^\s*(?:FAIL|BAD|ERROR|\u2717|\u2718)\b")


def strip(doc):
    """Everything the page rendered, as text."""
    doc = re.sub(r"(?s)<script.*?</script>", " ", doc)
    doc = re.sub(r"(?s)<style.*?</style>", " ", doc)
    # A tag boundary is a line boundary: several harnesses put each check in
    # its own <span>, and without this they run into one line and the
    # ^-anchored counts see one of them.
    doc = TAG.sub("\n", doc)
    return html.unescape(doc)


def main():
    only = sys.argv[1:] or None
    names = sorted(f for f in os.listdir(os.path.join(ROOT, "web", "_dev"))
                   if f.endswith(".html"))
    if only:
        names = [n for n in names if any(o in n for o in only)]

    rows = []
    for name in names:
        url = "%s/_dev/%s" % (BASE, name)
        if name not in NO_SESSION:
            url += "?session=" + urllib.parse.quote(SESSION, safe="")
        try:
            raw = subprocess.run(
                [EDGE, "--headless=new", "--disable-gpu",
                 # A real window. Headless defaults to something small, and
                 # the geometry harnesses measure against it: at the default
                 # size stratacheck reported six failures (rows 1px tall, 22
                 # buttons off screen) and typing reported 47 clipped names.
                 # Both pass at 1600x1000. A layout harness run in a 423px
                 # window is measuring the window, not the layout.
                 "--window-size=1600,1000",
                 "--virtual-time-budget=150000", "--dump-dom", url],
                capture_output=True, timeout=280, cwd=ROOT).stdout.decode(
                    "utf-8", "replace")
        except subprocess.TimeoutExpired:
            rows.append((name, 0, 0, "TIMED OUT", []))
            print("%-22s TIMED OUT" % name, flush=True)
            continue

        title = (re.search(r"<title>(.*?)</title>", raw, re.S) or [None, ""])[1]
        text = strip(raw)

        # Three ways a harness reports, all counted, largest wins. Reading
        # only the first meant every `#log`-style harness came back as
        # "0 checks" -- indistinguishable from a shot-taker, and a suite
        # where a third of the entries are unreadable looks like one that is
        # passing.
        ok = len(OK.findall(text))
        bad = len(BAD.findall(text))
        # Marker inside a span, so a line-anchored match sees the tag.
        span_ok = len(re.findall(r'class="good"', raw))
        span_bad = len(re.findall(r'class="bad"', raw))
        ok, bad = max(ok, span_ok), max(bad, span_bad)
        # And the ones that report only in the title.
        m = re.search(r"(\d+)\s*pass\D+(\d+)\s*fail", title or "")
        if m:
            ok, bad = max(ok, int(m.group(1))), max(bad, int(m.group(2)))
        m = re.search(r"(\d+)\s+FAILED", title or "")
        if m:
            bad = max(bad, int(m.group(1)))
        # "name: passed" is a pass with a count this runner cannot see. Say
        # so rather than filing it with the shot-takers.
        titled_pass = bool(re.search(r":\s*passed\s*$", (title or "").strip()))
        if titled_pass and not ok:
            ok = 1
        fails = [l.strip() for l in text.split("\n") if BAD.match(l)][:8]
        threw = "THREW" in text or "CRASH" in (title or "")
        note = ""
        if threw:
            note = next((l.strip() for l in text.split("\n")
                         if "THREW" in l), "").strip()[:90]
            if not note and "CRASH" in (title or ""):
                note = "title says CRASH"

        rows.append((name, ok, bad, note, fails))
        flag = "FAIL" if (bad or threw) else ("none" if not ok else "ok  ")
        print("%-22s %s  %4d ok  %3d fail  %s"
              % (name, flag, ok, bad,
                 note or (fails[0][:66] if fails else "")), flush=True)
        for f in fails[1:6]:
            print("%-22s          %s" % ("", f[:96]), flush=True)

    print("\n== tally ==")
    tot_ok = sum(r[1] for r in rows)
    tot_bad = sum(r[2] for r in rows)
    broken = [r[0] for r in rows if r[2] or r[3]]
    silent = [r[0] for r in rows if not r[1] and not r[2] and not r[3]]
    print("%d harness(es); %d check(s) passed, %d failed"
          % (len(rows), tot_ok, tot_bad))
    if broken:
        print("failing: " + ", ".join(broken))
    if silent:
        print("no checks reported (shot-takers and probes, mostly): "
              + ", ".join(silent))
    if not broken:
        print("nothing failing")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
