"""
onboard.py -- the two accounts a machine needs, asked for once, in Setup.

The Supabase key and the VACC sign-in used to be asked for by `start.py`,
every time Jarvis was activated on a machine that did not have them yet. The
user's ruling (2026-10-20): they belong to SETUP, the step somebody runs on
purpose to get a machine ready, and not to activation, which should just
open the app. So `setup.py` calls the two steps below. `start.py` only says
how things stand, in one line each, and never asks.

Both steps are skippable at every question. Jarvis writes locally first and
runs entirely without the network and without a cluster; neither account is
ever a prerequisite for starting.

VACC sign-in goes through `vacc.sign_in`, the same function the app's own
sign-in uses. Two implementations of one act was how the console version came
to lack a key-making step and the app's to lack nothing.
"""
from __future__ import annotations

import getpass
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(APP_DIR, "GUI_logs")


def _tty():
    return bool(sys.stdin and sys.stdin.isatty())


def _ask_line(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _ask_secret(prompt):
    """A secret, not echoed. None when this console cannot hide one."""
    try:
        return getpass.getpass(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    except Exception:                                    # noqa: BLE001
        return None


def _yes(prompt, default=False):
    raw = _ask_line(prompt + (" [Y/n] " if default else " [y/N] ")).lower()
    if not raw:
        return default
    return raw in ("y", "yes")


# --------------------------------------------------------------------------
# How things stand, one line each (start.py prints these)
# --------------------------------------------------------------------------
def cloud_line(logs_dir=LOGS_DIR):
    from backend import cloud
    cfg = cloud.load_config(logs_dir)
    if cfg.get("key_in_repo"):
        return ("Sync    : the key in cloud.json is tracked by git and is "
                "ignored -- rotate it, then run Setup again")
    if cfg.get("needs_key"):
        return "Sync    : off -- no key on this machine (run Setup to add it)"
    if cfg.get("enabled"):
        return "Sync    : %s" % cfg.get("project")
    return "Sync    : switched off here"


def vacc_line(logs_dir=LOGS_DIR):
    from backend import vacc
    cfg = vacc.load_config(logs_dir)
    if cfg.get("configured"):
        return "VACC    : signed in as %s@%s" % (cfg.get("netid"),
                                                  cfg.get("host"))
    if not vacc.have_ssh():
        return "VACC    : no ssh client on this machine"
    return ("VACC    : not set up -- run Setup, or sign in from your "
            "profile in the app")


# --------------------------------------------------------------------------
# Setup's two steps
# --------------------------------------------------------------------------
def cloud_step(logs_dir=LOGS_DIR, say=print):
    """Give this machine the Supabase key, or keep the one it has."""
    from backend import cloud

    cfg = cloud.load_config(logs_dir)
    say("")
    say("  Shared database (Supabase)")
    if cfg.get("key_in_repo"):
        say("  !! cloud.json in the repo contains a key. That file is")
        say("     tracked by git, so treat the key as public: rotate it in")
        say("     the Supabase dashboard and paste the new one below.")
    elif not cfg.get("needs_key"):
        say("  This machine already has the key for '%s'." % cfg.get("project"))
        if not _tty() or not _yes("  Replace it?", default=False):
            return True
    if not _tty():
        say("  (not a terminal, so skipping the question)")
        return False

    say("  This copy syncs to Supabase project '%s'." % cfg.get("project"))
    say("  Get the key from the dashboard: Project Settings -> API Keys ->")
    say("  secret / service_role. It is kept in GUI_logs/.cloud.json, which")
    say("  git ignores. Press Enter to skip -- Jarvis works without it.")
    for _ in range(3):
        key = _ask_secret("  Supabase secret key (paste it; not shown): ")
        if key is None:
            key = _ask_line("  Supabase secret key: ")
        key = (key or "").strip()
        if not key:
            say("  Skipped. Sync stays off until a key is set.")
            return False
        ok, why = cloud.looks_like_a_key(key)
        if not ok:
            say("  %s" % why)
            continue
        cloud.save_config(logs_dir, key=key)
        say("  Checking...")
        ping = cloud.Cloud(logs_dir).ping()
        if not ping["reachable"]:
            say("  Could not reach the project: %s"
                % (ping.get("error") or "")[:160])
            say("  Saved anyway; Jarvis keeps trying in the background.")
            return True
        if not ping["schema"]:
            say("  Connected, but the tables are not there yet. Run the SQL in")
            say("  supabase/ (01_schema, 02_rls, 03_storage), then")
            say("  python tools/cloud_migrate.py --write")
            return True
        n = sum(v for v in (ping.get("counts") or {}).values()
                if isinstance(v, int))
        say("  Connected. %d row(s) already up there." % n)
        return True
    say("  Skipping for now. Run Setup again to add it.")
    return False


def vacc_step(logs_dir=LOGS_DIR, say=print):
    """Sign this machine in to the VACC, through `vacc.sign_in`."""
    from backend import vacc

    cfg = vacc.load_config(logs_dir)
    say("")
    say("  VACC (the cluster)")
    if not vacc.have_ssh():
        say("  No ssh client on this machine, so the cluster is out of reach.")
        return False
    if cfg.get("configured"):
        say("  Signed in as %s@%s." % (cfg.get("netid"), cfg.get("host")))
        if not _tty() or not _yes("  Sign in as somebody else?",
                                  default=False):
            return True
    if not _tty():
        say("  (not a terminal, so skipping the question)")
        return False

    say("  Jarvis can run Incisor, Doppler and more on the VACC if you have")
    say("  an account. It needs your NetID -- the part of your UVM email")
    say("  before the @. Press Enter to skip.")
    netid = _ask_line("  UVM NetID: ")
    if not netid:
        say("  Skipped. You can sign in later from your profile in the app.")
        return False
    if not vacc.NETID_RE.match(netid):
        say("  That does not look like a NetID (letters and digits, no")
        say("  spaces, no @). Skipping -- run Setup again to retry.")
        return False

    tries = []
    note = tries.append
    say("  Checking the keys already on this computer...")
    try:
        got = vacc.sign_in(logs_dir, netid, note=note)
    except vacc.SSHError as exc:
        if exc.kind != "need-password":
            say("  That did not work: %s" % str(exc)[:200])
            return False
        say("")
        say("  No key on this computer works for %s yet, so your UVM" % netid)
        say("  password is needed ONCE to install one. It is used for that one")
        say("  connection and dropped: not written down, not logged. Approve")
        say("  the Duo push when it arrives. Press Enter to skip.")
        password = _ask_secret("  UVM password (not shown): ")
        if password is None:
            say("  This console cannot hide a password. Sign in from your")
            say("  profile inside the app instead.")
            return False
        if not password:
            say("  Skipped. You can sign in later from your profile in the app.")
            return False
        say("  Installing a key (check your phone for the Duo push)...")
        try:
            got = vacc.sign_in(logs_dir, netid, password=password, note=note)
        except vacc.SSHError as exc2:
            say("  That did not work: %s" % str(exc2)[:200])
            if tries:
                say("  (%d key check(s) were refused before it gave up.)"
                    % len(tries))
            return False
        finally:
            password = None
    say("  Signed in as %s. The app will open signed in, with VACC Mode on."
        % got["netid"])
    if tries:
        say("  (the cluster refused the new key %d time(s) before accepting it"
            ")" % len(tries))
    return True
