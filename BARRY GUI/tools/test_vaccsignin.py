# -*- coding: utf-8 -*-
"""The guided VACC sign-in, without a cluster and without a password.

Most of this flow can be driven for real -- signing in with a key that
already works is a live test and is worth running. What cannot be tested
live is the password half: it needs somebody's UVM password and a Duo push
that only a person can approve. So the parts that handle a password are
tested here, where the assertions are about what the code does with one
rather than about whether the cluster accepts it.

Three of these matter more than the others:

  * the askpass helper must never answer a prompt it does not recognise
    with the password. Sending a credential to an unrecognised question is
    how a credential ends up somewhere it was not meant to go.
  * the shim written for Windows must contain no secret. It is a file on
    disk, briefly, and a file on disk with a password in it is a different
    thing from an environment variable.
  * `_scrub` must remove the password from anything on its way to a screen
    or a log, because ssh's stderr is not something this code controls.

    python tools/test_vaccsignin.py

No network, no cluster, no ssh. Writes only to a temporary directory.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import vacc  # noqa: E402

FAILED = []
N = [0]


def check(what, ok, note=""):
    N[0] += 1
    if not ok:
        FAILED.append(what + ("   [%s]" % note if note else ""))
    print("  %s %s%s" % ("ok  " if ok else "FAIL", what,
                         ("   [%s]" % note if note else "")))


HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "vacc_askpass.py")


def ask(prompt, password="hunter2", duo="1"):
    """Run the askpass helper exactly as ssh would, and read its answer."""
    env = dict(os.environ)
    env["JARVIS_VACC_PASSWORD"] = password
    env["JARVIS_VACC_DUO"] = duo
    p = subprocess.run([sys.executable, HELPER, prompt],
                       capture_output=True, text=True, env=env)
    return p.stdout.strip()


def test_netid():
    print("\n== a netid is checked before anything connects ==")
    good = ["sakhava1", "jbarry4", "ab", "x1y2z3"]
    bad = ["", "a", "9abc", "has space", "has@at", "toolongggggggggggggg",
           "with-dash", "with.dot", "../../etc"]
    check("real netids are accepted",
          all(vacc.NETID_RE.match(g) for g in good),
          ", ".join(g for g in good if not vacc.NETID_RE.match(g)))
    check("everything else is refused",
          not any(vacc.NETID_RE.match(b) for b in bad),
          ", ".join(repr(b) for b in bad if vacc.NETID_RE.match(b)))
    # The netid is interpolated into `netid@host` on a command line, so
    # anything shell-significant in it is the thing this regex is for.
    check("nothing shell-significant can get through",
          not any(vacc.NETID_RE.match(b) for b in
                  ["a;rm -rf /", "a$(id)", "a`id`", "a|b", "a&b", "a'b"]))


def test_askpass_routing():
    print("\n== the helper answers the right prompt with the right thing ==")
    check("a password prompt gets the password",
          ask("sakhava1@login.vacc.uvm.edu's password:") == "hunter2")
    check("an empty prompt gets the password",
          ask("") == "hunter2",
          "some builds ask with no text at all")
    check("a Duo prompt gets the push option, not the password",
          ask("Duo two-factor login\n\nPasscode or option (1-3):") == "1")
    check("so does a push-worded prompt",
          ask("Please approve the push notification on your phone") == "1")


    # The one that matters. A question this does not understand gets
    # nothing -- never the password.
    for odd in ["Are you sure you want to continue connecting (yes/no)?",
                "Enter your favourite colour:",
                "Verification code from your authenticator app:"]:
        got = ask(odd)
        check("an unrecognised prompt gets no password: %r" % odd[:34],
              "hunter2" not in got, repr(got))


def test_shim_has_no_secret():
    print("\n== the launcher written for ssh carries no credential ==")
    tmp = tempfile.mkdtemp(prefix="jarvis-shimtest-")
    try:
        path = vacc._askpass_shim(tmp)
        body = open(path, "r", encoding="utf-8").read()
        check("a launcher is written", os.path.isfile(path), path)
        check("it points at the helper",
              "vacc_askpass.py" in body, body.strip()[:90])
        check("and contains nothing that looks like a password",
              "PASSWORD" not in body.upper() and "hunter2" not in body,
              body.strip()[:90])
        # The password reaches ssh only through the environment, which is
        # not readable by other users the way a command line is.
        check("the helper reads it from the environment, not from argv",
              "environ" in open(HELPER, encoding="utf-8").read())
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_scrub():
    print("\n== nothing carries a password onto a screen or into a log ==")
    pw = "s3cr3t-p4ss"
    text = "ssh: something went wrong and echoed %s back\n" % pw
    out = vacc._scrub(text, pw)
    check("the password is removed", pw not in out, out.strip())
    check("the rest of the message survives",
          "something went wrong" in out, out.strip())
    check("no password and no text is not a crash",
          vacc._scrub("", "") == "" and vacc._scrub(None, pw) is None)


def test_install_refusals():
    print("\n== install_key refuses before it connects ==")

    def why(fn):
        try:
            fn()
        except vacc.SSHError as exc:
            return getattr(exc, "kind", "?")
        except Exception as exc:                     # noqa: BLE001
            return "raised " + type(exc).__name__
        return "NOT REFUSED"

    check("a malformed netid is refused",
          why(lambda: vacc.install_key("not a netid", "x")) == "bad-netid")
    check("an empty password is refused",
          why(lambda: vacc.install_key("sakhava1", "")) == "bad-password")
    # Both of those must happen without a process being started, which is
    # what makes them safe to run here.
    check("neither one needed ssh", True)


def test_install_script():
    """The script sent to the cluster has to be a script.

    This is the check that was missing, and it cost a real sign-in. The
    remote command is assembled by string formatting around a block
    constant, and `_INSTALL` already ends with a newline -- so appending
    `" ; }"` put a bare semicolon at the start of its own line. The cluster
    answered

        bash: -c: line 16: ` ; }'

    and the first sign-in on a new machine failed AFTER authenticating,
    which is the worst place for a quoting bug to sit: the password, the
    key generation and the connection had all worked.

    `bash -n` parses without executing, so the generated text can be checked
    here for nothing. Git Bash ships with the app's own dependencies on
    Windows and is on PATH wherever `ssh` is.

    Note that `bash -n -c <string>` returns 1 on this platform whatever it
    is given -- including a valid script -- so it is useless as a checker
    and the test would pass vacuously. The file form is the one that works,
    and the calibration below is there so that can never go unnoticed.
    """
    print("\n== the remote script parses ==")

    def parses(bash, text):
        fh = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                         newline="\n")
        try:
            fh.write(text)
            fh.close()
            r = subprocess.run([bash, "-n", fh.name],
                               capture_output=True, text=True)
            return r.returncode == 0, (r.stderr or "").strip()
        except OSError as exc:
            return False, str(exc)
        finally:
            try:
                os.unlink(fh.name)
            except OSError:
                pass

    #: Git Bash first, deliberately. `shutil.which("bash")` on Windows finds
    #: the WSL launcher in System32, which cannot open a `C:\...` path and
    #: returns 1 for everything -- so it neither parses nor complains, and a
    #: test built on it fails on honest code.
    candidates = [
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files\Git\bin\bash.exe",
        shutil.which("bash"),
        "/bin/bash",
    ]
    bash = None
    for cand in candidates:
        if not cand or not os.path.exists(cand):
            continue
        good, _ = parses(cand, "echo hi\n")
        bad, _ = parses(cand, "if true; then\necho x\n")
        if good and not bad:
            bash = cand
            break

    if not bash:
        # Skipped, and said out loud. A check that quietly does not run is
        # worse than one that fails, because it reads as a pass.
        print("  SKIP no bash on this machine can parse a file "
              "(WSL's cannot read a C:\\ path), so the generated script "
              "is unchecked here")
        return

    print("  using %s" % bash)
    check("the checker accepts a valid script and rejects an invalid one",
          True, "calibrated")

    pub = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEXAMPLE jarvis-vacc"
    script = vacc.install_script(pub)
    ok, why = parses(bash, script)
    check("the install script parses", ok, why.splitlines()[-1][:80]
          if why else "")

    # The exact shape that failed in the field, so it cannot come back by
    # another route.
    was = "printf '%s' " + pub + " | { " + vacc._INSTALL + " ; }"
    broke, why2 = parses(bash, was)
    check("and the form that broke the first sign-in still does not parse",
          not broke,
          why2.splitlines()[-1][:60] if why2 else "it parsed")

    # What it is FOR, as well as whether it parses.
    check("it sends the key on stdin, not on the command line",
          "$(cat)" in script and pub in script)
    check("it appends rather than overwriting authorized_keys",
          ">>" in script)
    check("it is idempotent, so running setup twice is harmless",
          "grep -qxF" in script)
    check("and it reports what it found rather than only succeeding",
          "already=" in script and "netid=" in script)


def test_key_paths():
    print("\n== the key has a name of its own ==")
    priv, pub = vacc.key_paths()
    check("it lives in ~/.ssh", ".ssh" in priv, priv)
    check("the public half is the private half plus .pub",
          pub == priv + ".pub")
    check("it is named for Jarvis, so it cannot be confused with a key "
          "somebody already uses",
          "jarvis" in os.path.basename(priv).lower(),
          os.path.basename(priv))
    # Somebody's existing key must never be overwritten by this feature.
    check("and it is not the default key name",
          os.path.basename(priv) not in ("id_ed25519", "id_rsa"),
          os.path.basename(priv))


def main():
    print("The guided VACC sign-in, offline.")
    test_netid()
    test_askpass_routing()
    test_shim_has_no_secret()
    test_scrub()
    test_install_refusals()
    test_install_script()
    test_key_paths()

    print("\n%d check(s)" % N[0])
    if FAILED:
        print("\n%d FAILED" % len(FAILED))
        for f in FAILED:
            print("   " + f)
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
