# -*- coding: utf-8 -*-
"""The lab's one-time SoftMouse sign-in set-up (backend/softmouse_login.py).

Reads a two-line text file (username, then password), seals it with the PIN,
puts the sealed copy in the cloud for every Jarvis with the sync, keeps it on
this machine, and checks it opens again. Prints neither line. Delete the text
file afterwards: the repo is public.

    python tools/softmouse_login_setup.py FILE --pin PIN [--by NAME] [--test]

--test also signs in to SoftMouse with it, in a Chrome nobody sees, and
reads one row of the Mouse List.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from backend import softmouse, softmouse_login as login  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--pin", required=True)
    ap.add_argument("--by")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    with open(a.file, encoding="utf-8-sig") as fh:
        lines = [ln.strip() for ln in fh.read().splitlines() if ln.strip()]
    if len(lines) != 2:
        sys.exit("expected two lines (username, password), found %d" % len(lines))
    username, password = lines
    login.publish(username, password, a.pin, by=a.by)
    print("sealed and sent to %s/%s" % (login.BUCKET, login.KEY))
    blob = login.fetch()
    assert login.open_sealed(blob, a.pin) == (username, password), "cloud copy differs"
    try:
        login.open_sealed(blob, "00000")
        sys.exit("a wrong PIN opened it")
    except login.WrongPin:
        pass
    assert login.here() == (username, password), "this machine's copy differs"
    print("the cloud copy opens with the PIN and not without; this machine keeps it")
    if a.test:
        kept = softmouse._jar()
        softmouse._write(softmouse.JAR, [])        # start signed out, for real
        try:
            softmouse._auto_login(username, password)
        except Exception:
            softmouse._write(softmouse.JAR, kept)  # the session that worked
            raise
        print("signed in by itself; Mouse List answers:", softmouse.check_session())


if __name__ == "__main__":
    main()
