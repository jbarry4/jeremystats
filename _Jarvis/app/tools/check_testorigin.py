# -*- coding: utf-8 -*-
"""A harness's faults are a test's, wherever the harness runs.

2026-10-30: web/_dev/rootcanalborder.html, run against the live app rather
than the harness server, filed its refusal on purpose -- "The border
hb-other is not on this machine" -- as a real fault, and it led Bluebarry's
end-of-day report. The server knew a harness only by the referrer, and a
request from the app in the harness's frame names the frame. The frame now
says so (X-Barry-Test, web/js/core.js), and `_request_is_test` listens.

It got there by tools/harness_run.ps1, the runner the daily triage uses,
which started its server without BARRY_HARNESS_SERVER (harness_run.py sets
it), and its `-Names a,b` reached run_harnesses.py as one argument that
matched nothing: "0 harness(es) ... nothing failing". Both are held here.

No server and nothing written: each case is a request context and the
answer `_request_is_test` gives inside it. web/_dev/testorigin.html checks
the other half, that the frame sends the header.

    python tools/check_testorigin.py
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import app as A  # noqa: E402

ok = bad = 0
APP = "http://127.0.0.1:8733"


def check(name, got, want=True):
    global ok, bad
    if got == want:
        ok += 1
        print("  ok    %s" % name)
    else:
        bad += 1
        print("  FAIL  %s\n        got %r, want %r" % (name, got, want))


def is_test(headers, base=APP):
    with A.app.test_request_context("/api/rootcanal/pool/fit",
                                    method="POST", base_url=base,
                                    headers=headers):
        return A._request_is_test()


print("a request is a test's when")
check("it comes from the app in a harness's frame (X-Barry-Test)",
      is_test({"Referer": APP + "/", "X-Barry-Test": "1"}))
check("it comes from a harness page itself (its referrer)",
      is_test({"Referer": APP + "/_dev/rootcanalborder.html"}))
check("it comes from Flask's test client (host localhost)",
      is_test({}, base="http://localhost"))

print("and a person's is not")
check("the app at the top of its own tab",
      is_test({"Referer": APP + "/"}), False)
check("a request with no referrer at all",
      is_test({}), False)

print("harness_run.ps1 starts a harness server")
with open(os.path.join(HERE, "harness_run.ps1"), encoding="utf-8") as fh:
    ps1 = fh.read()
flag = re.search(r'^\s*\$env:BARRY_HARNESS_SERVER\s*=\s*"1"', ps1, re.M)
start = re.search(r"^\s*\$p\s*=\s*Start-Process", ps1, re.M)
check("it sets BARRY_HARNESS_SERVER before it starts the server",
      bool(flag and start and flag.start() < start.start()))

print("and the runner runs every harness it is told to")
spec = importlib.util.spec_from_file_location(
    "run_harnesses", os.path.join(HERE, "run_harnesses.py"))
RH = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RH)
files = ["bounce.html", "rootcanalborder.html", "rootcanalswitch.html",
         "testorigin.html"]
check("-Names a,b under powershell -File (one argument, with a comma)",
      RH.pick(files, ["testorigin,rootcanalborder"]),
      (["rootcanalborder.html", "testorigin.html"], []))
check("names as separate arguments, as before",
      RH.pick(files, ["bounce", "switch"]),
      (["bounce.html", "rootcanalswitch.html"], []))
check("a name that matches nothing is said, not run as a clean sweep",
      RH.pick(files, ["bounce,nosuchharness"]),
      (["bounce.html"], ["nosuchharness"]))
check("no names is every harness",
      RH.pick(files, []), (files, []))

print("%d ok, %d fail" % (ok, bad))
sys.exit(1 if bad else 0)
