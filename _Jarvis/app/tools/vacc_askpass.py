# -*- coding: utf-8 -*-
"""Answer ssh's prompts during the one-time VACC key install.

WHY THIS EXISTS AT ALL

`ssh` does not read a password from stdin. It opens the console directly, so
piping one in does nothing -- the prompt appears and the pipe is ignored.
OpenSSH's own answer to that is `SSH_ASKPASS`: a program it runs to obtain
each prompt's answer, forced on with `SSH_ASKPASS_REQUIRE=force` (OpenSSH
8.4 and later; Windows ships 9.5).

So this is that program. It is run once per prompt, prints one answer, and
exits.

WHERE THE PASSWORD IS, AND WHERE IT IS NOT

In this process's environment, put there by the parent for the lifetime of
one `ssh` invocation. It is never written to a file, never on a command
line (where it would be visible to every other process on the machine),
never logged, and never sent anywhere except to the ssh process that asked.
The parent discards it as soon as ssh exits.

The `.bat` shim the parent writes so that Windows can execute this contains
no secret either -- only the path to the interpreter and the path to this
file.

THE TWO PROMPTS

Logging in with a password at UVM is two questions, not one: the password,
and then Duo. ssh passes the prompt text as argv[1], which is how they are
told apart. Anything that is not asking for a password is Duo, and the
answer is 1 -- "push" -- so the person approves it on their phone. There is
deliberately no attempt to type a passcode: this runs unattended and a
wrong guess at a second factor is worse than a prompt that waits.

A prompt this does not recognise gets an empty line rather than the
password. Sending a password to an unrecognised question is how a password
ends up somewhere it was not meant to go.
"""
import os
import re
import sys

PASSWORD_RE = re.compile(r"password|passphrase", re.I)
DUO_RE = re.compile(r"duo|passcode|option \(|push|two-factor|2fa", re.I)


def main():
    prompt = " ".join(sys.argv[1:])

    if PASSWORD_RE.search(prompt):
        sys.stdout.write(os.environ.get("JARVIS_VACC_PASSWORD", "") + "\n")
        return 0

    if DUO_RE.search(prompt):
        # 1 is "Duo Push" in UVM's factor list. The person approves it on
        # their phone; nothing here can or should approve it for them.
        sys.stdout.write(os.environ.get("JARVIS_VACC_DUO", "1") + "\n")
        return 0

    # An empty prompt is the usual shape of the very first password ask on
    # some builds, so it gets the password. Anything else with actual words
    # in it that this does not recognise gets nothing.
    if not prompt.strip():
        sys.stdout.write(os.environ.get("JARVIS_VACC_PASSWORD", "") + "\n")
        return 0

    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
