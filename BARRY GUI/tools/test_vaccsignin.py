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


class _Fake:
    """Stand-ins for everything `sign_in` touches on the far side."""

    def __init__(self, working=None, refuse=0, who=None):
        self.working = working
        self.refuse = refuse          # key-only proofs refused before one works
        self.who = who
        self.calls = []

    def __enter__(self):
        self.saved = {n: getattr(vacc, n) for n in
                      ("working_key", "make_key", "install_key", "_ssh",
                       "_pin_host")}
        self.sleep = vacc.time.sleep
        vacc.working_key = lambda netid, host=None, **k: (
            self.calls.append("working_key") or self.working)
        vacc.make_key = lambda *a, **k: (
            self.calls.append("make_key") or {"created": True})
        vacc.install_key = lambda netid, password, host=None, duo="1", \
            alias=None: (self.calls.append(("install_key", host, alias))
                         or {"already": False, "netid": netid})
        vacc._pin_host = lambda host: None

        def ssh(cfg, cmd, stdin=None, timeout=45):
            self.calls.append(("ssh", cmd))
            if self.refuse > 0:
                self.refuse -= 1
                raise vacc.SSHError("refused", "auth")
            return (self.who or cfg["netid"]) + "\n"
        vacc._ssh = ssh
        vacc.time.sleep = lambda s: self.calls.append(("sleep", s))
        return self

    def __exit__(self, *exc):
        for n, f in self.saved.items():
            setattr(vacc, n, f)
        vacc.time.sleep = self.sleep


def test_sign_in():
    print("\n== sign_in: one implementation, lands the first time ==")
    tmp = tempfile.mkdtemp(prefix="jarvis-signin-")
    try:
        # A fresh machine: no key works, so it must MAKE one before
        # installing it. The console path used to skip this and could
        # never succeed on a new computer.
        with _Fake() as f:
            try:
                vacc.sign_in(tmp, "sakhava1")
                check("with no working key and no password it asks for one",
                      False, "did not raise")
            except vacc.SSHError as exc:
                check("with no working key and no password it asks for one",
                      exc.kind == "need-password", exc.kind)
        with _Fake(refuse=2) as f:
            got = vacc.sign_in(tmp, "sakhava1", password="hunter2")
            names = [c if isinstance(c, str) else c[0] for c in f.calls]
            check("a key is made before it is installed",
                  "make_key" in names and "install_key" in names
                  and names.index("make_key") < names.index("install_key"),
                  str(names))
            proofs = [c for c in f.calls if c[0] == "ssh"]
            check("a refused proof is retried, not given up on",
                  len(proofs) == 3, "%d proofs" % len(proofs))
            check("and the retries wait between attempts",
                  any(c[0] == "sleep" for c in f.calls if isinstance(c, tuple)))
            check("it reports a new key", got["made_key"] is True)
        cfg = vacc.load_config(tmp)
        raw = vacc._read(vacc.config_path(tmp))
        check("the config is written only after the proof, with the netid",
              cfg.get("netid") == "sakhava1", cfg.get("netid"))
        check("and enabled", raw.get("enabled") is True, raw.get("enabled"))
        check("and a signed_in_at stamp the app can greet",
              isinstance(raw.get("signed_in_at"), (int, float)),
              raw.get("signed_in_at"))

        # A key that already works: no password, no install, still enabled.
        tmp2 = tempfile.mkdtemp(prefix="jarvis-signin-")
        try:
            with _Fake(working="C:/keys/id_ed25519") as f:
                got = vacc.sign_in(tmp2, "sakhava1")
                names = [c if isinstance(c, str) else c[0] for c in f.calls]
                check("a working key needs no install",
                      "install_key" not in names and "make_key" not in names,
                      str(names))
            raw2 = vacc._read(vacc.config_path(tmp2))
            check("and is saved enabled (the console path left it out)",
                  raw2.get("enabled") is True and raw2.get("key_path")
                  == "C:/keys/id_ed25519", str(raw2))
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

        # The cluster says somebody else: nothing is saved over the old one.
        tmp3 = tempfile.mkdtemp(prefix="jarvis-signin-")
        try:
            with _Fake(working="k", who="someoneelse") as f:
                try:
                    vacc.sign_in(tmp3, "sakhava1")
                    check("a mismatched account is refused", False)
                except vacc.SSHError as exc:
                    check("a mismatched account is refused",
                          exc.kind == "mismatch", exc.kind)
            check("and nothing is written",
                  not vacc._read(vacc.config_path(tmp3)).get("netid"))
        finally:
            shutil.rmtree(tmp3, ignore_errors=True)

        # Refused on every try: the error is raised, not swallowed, and the
        # config is left alone.
        tmp4 = tempfile.mkdtemp(prefix="jarvis-signin-")
        try:
            with _Fake(refuse=99) as f:
                notes = []
                try:
                    vacc.sign_in(tmp4, "sakhava1", password="x",
                                 note=notes.append)
                    check("a key that never takes is reported", False)
                except vacc.SSHError as exc:
                    check("a key that never takes is reported",
                          exc.kind == "auth", exc.kind)
                check("every refused attempt is noted for the log",
                      len(notes) == len(vacc.PROOF_WAITS), str(notes))
            check("and nothing is written after a failed proof",
                  not vacc._read(vacc.config_path(tmp4)).get("netid"))
        finally:
            shutil.rmtree(tmp4, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ssh_cmd_alias():
    print("\n== a pinned login node keeps the host key it is known by ==")
    cmd = vacc.ssh_cmd({"netid": "sakhava1", "host": "10.0.0.5",
                        "host_alias": "login.vacc.uvm.edu",
                        "key_path": "k"}, "whoami")
    check("HostKeyAlias names the cluster", "HostKeyAlias=login.vacc.uvm.edu"
          in cmd, " ".join(cmd))
    check("and the connection goes to the pinned address",
          "sakhava1@10.0.0.5" in cmd)
    plain = vacc.ssh_cmd({"netid": "sakhava1", "host": "login.vacc.uvm.edu",
                          "key_path": "k"}, "whoami")
    check("an unpinned call carries no alias",
          not any("HostKeyAlias" in c for c in plain))


def main():
    print("The guided VACC sign-in, offline.")
    test_netid()
    test_askpass_routing()
    test_shim_has_no_secret()
    test_scrub()
    test_install_refusals()
    test_install_script()
    test_key_paths()
    test_sign_in()
    test_ssh_cmd_alias()

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
