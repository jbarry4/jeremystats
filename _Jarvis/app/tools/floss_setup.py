# -*- coding: utf-8 -*-
"""The lab's one-time Floss set-up (backend/floss_key.py).

Seals the lab account's Claude key with the PIN, puts the sealed copy in the
cloud for every Jarvis with the sync, keeps it on this machine, and checks
it opens again. Prints no key. The key is typed (hidden) unless a file is
given; delete any such file afterwards: the repo is public.

    python tools/floss_setup.py --pin PIN [KEYFILE | --clipboard] [--by NAME] [--test]

--clipboard takes the key from the clipboard (line breaks a console wrap
put in are dropped) and empties the clipboard afterwards.

The key is either kind:
    claude setup-token     signed in as the lab account -> sk-ant-oat...
                           (uses the plan's limits; no per-token bill)
    console.anthropic.com  an API key -> sk-ant-api... (billed per token;
                           Floss caps each run at $2)

--test also asks Claude one word with it, through the same locked-down
Claude Code Floss uses, to show the key and the engine work together.
"""
import argparse
import getpass
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from backend import floss, floss_key as key  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--pin", required=True)
    ap.add_argument("--by")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--clipboard", action="store_true")
    a = ap.parse_args()
    if a.clipboard:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                           capture_output=True)
        secret = "".join(r.stdout.decode("utf-8", "replace").split())
        subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ' '"],
                       capture_output=True)
        m = re.search(r"sk-ant-(?:oat|api)[0-9A-Za-z_-]+", secret)
        secret = m.group(0) if m else secret
    elif a.file:
        with open(a.file, encoding="utf-8-sig") as fh:
            secret = fh.read().strip()
    else:
        secret = getpass.getpass("Claude key (hidden): ").strip()
    if not key.kind_of(secret):
        sys.exit("that is not a Claude key: expected sk-ant-oat... or sk-ant-api...")
    key.publish(secret, a.pin, by=a.by)
    print("sealed (%s) and sent to %s/%s" % (key.kind_of(secret), key.BUCKET, key.KEY))
    blob = key.fetch()
    assert key.open_sealed(blob, a.pin) == secret, "cloud copy differs"
    try:
        key.open_sealed(blob, "00000")
        sys.exit("a wrong PIN opened it")
    except key.WrongPin:
        pass
    assert key.here() == secret, "this machine's copy differs"
    print("the cloud copy opens with the PIN and not without; this machine keeps it")
    if a.test:
        exe = floss.engine()
        if not exe:
            sys.exit("no Claude Code on this machine to test with (Floss's dialog installs it)")
        os.makedirs(floss.HOME, exist_ok=True)
        r = subprocess.run([exe, "-p", "--model", "haiku", "--tools", "", "--restricted",
                            "--strict-mcp-config", "--no-session-persistence",
                            "Reply with the single word OK."],
                           env=floss._env(secret), capture_output=True, timeout=120)
        said = r.stdout.decode("utf-8", "replace").strip()
        print("Claude said: %s" % (said or r.stderr.decode("utf-8", "replace").strip()))
        if r.returncode or "OK" not in said.upper():
            sys.exit("the test did not come back OK")


if __name__ == "__main__":
    main()
