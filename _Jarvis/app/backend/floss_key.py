"""
floss_key.py -- the lab's Claude key for Floss, the on-demand bug fixer.

The same arrangement as the SoftMouse sign-in (softmouse_login.py), for the
same reasons, and built from its cipher rather than a second one:

    The shared copy   Supabase storage, bucket "results" (private), object
                      jarvis-secrets/floss-key.txt, sealed with the lab PIN.
                      NOT the repo: jbarry4/jeremystats is public.
    This machine's    %LOCALAPPDATA%\\Jarvis\\floss\\key.bin, sealed with
                      Windows DPAPI once somebody types the PIN. (Elsewhere,
                      ~/.jarvis/floss/key.bin readable by this user only.)

THE KEY is one of two kinds, and Floss runs the same either way:

    sk-ant-oat...   a Claude subscription token, from `claude setup-token`
                    signed in as the lab account. Given to Claude Code as
                    CLAUDE_CODE_OAUTH_TOKEN; spends the plan's usage limits.
    sk-ant-api...   a Console API key (console.anthropic.com). Given as
                    ANTHROPIC_API_KEY; billed per token, so each run also
                    gets a dollar cap.

Set up once, from any machine with the cloud sync:
    python tools/floss_setup.py KEYFILE --pin PIN
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import time

from . import softmouse_login as sm

BUCKET = "results"
KEY = "jarvis-secrets/floss-key.txt"
HINT = sm.HINT                     # the same PIN as SoftMouse, unless set up otherwise

if sys.platform == "win32":
    STATE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                         "Jarvis", "floss")
else:
    STATE = os.path.join(os.path.expanduser("~"), ".jarvis", "floss")
LOCAL = os.path.join(STATE, "key.bin")

_TRIES = {"wrong": 0, "until": 0.0}
_TRIES_LOCK = threading.Lock()


class WrongPin(ValueError):
    pass


def kind_of(key):
    """'oauth', 'api', or None for something that is neither."""
    key = (key or "").strip()
    if key.startswith("sk-ant-oat"):
        return "oauth"
    if key.startswith("sk-ant-api"):
        return "api"
    return None


# --- the cipher (softmouse_login's, with Floss's own MAC label) ----------------

def _mac(key, nonce, ct):
    return hmac.new(key, b"jarvis-floss-v1" + nonce + ct, hashlib.sha256).digest()


def seal(secret, pin, by=None):
    salt, nonce = os.urandom(16), os.urandom(16)
    ek, mk = sm._keys(pin, salt, sm.SCRYPT)
    pt = json.dumps({"key": secret}).encode()
    ct = bytes(a ^ b for a, b in zip(pt, sm._stream(ek, nonce, len(pt))))
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 1, "what": "Claude key for Hater of AI (Jarvis, backend/floss.py)", "hint": HINT,
            "kind": kind_of(secret),
            "kdf": dict(sm.SCRYPT, name="scrypt"), "salt": b64(salt), "nonce": b64(nonce),
            "ct": b64(ct), "tag": b64(_mac(mk, nonce, ct)),
            "by": by, "at": time.strftime("%Y-%m-%d %H:%M")}


def open_sealed(blob, pin):
    d = lambda k: base64.b64decode(blob[k])
    salt, nonce, ct = d("salt"), d("nonce"), d("ct")
    ek, mk = sm._keys(pin, salt, blob["kdf"])
    if not hmac.compare_digest(_mac(mk, nonce, ct), d("tag")):
        raise WrongPin("that PIN does not open it")
    pt = bytes(a ^ b for a, b in zip(ct, sm._stream(ek, nonce, len(ct))))
    return json.loads(pt.decode())["key"]


# --- this machine ----------------------------------------------------------------

def _keep_here(secret):
    os.makedirs(STATE, exist_ok=True)
    raw = json.dumps({"key": secret}).encode()
    sealed = sm._dpapi(raw, True) if sys.platform == "win32" else raw
    fd, tmp = tempfile.mkstemp(dir=STATE, suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(sealed)
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)
    os.replace(tmp, LOCAL)


def here():
    """The key on this machine, or None."""
    try:
        with open(LOCAL, "rb") as fh:
            raw = fh.read()
        if sys.platform == "win32":
            raw = sm._dpapi(raw, False)
        return json.loads(raw.decode())["key"]
    except (OSError, ValueError, KeyError):
        return None


def forget_here():
    try:
        os.remove(LOCAL)
    except FileNotFoundError:
        pass


# --- the shared copy ---------------------------------------------------------------

def _cloud():
    from . import cloud
    from .paths import LOGS_DIR
    c = cloud.Cloud(LOGS_DIR)
    if not c.configured:
        raise RuntimeError("this Jarvis has no cloud sync, so it cannot fetch the "
                           "lab's key for Hater of AI")
    return c


def publish(secret, pin, by=None):
    if not kind_of(secret):
        raise ValueError("that is not a Claude key: expected sk-ant-oat... "
                         "(claude setup-token) or sk-ant-api... (Console)")
    blob = seal(secret, pin, by=by)
    if open_sealed(blob, pin) != secret:
        raise RuntimeError("the sealed copy did not open again; nothing was sent")
    fd, tmp = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(base64.b64encode(json.dumps(blob).encode()))
        _cloud().upload(BUCKET, KEY, tmp, content_type="text/plain")
    finally:
        os.remove(tmp)
    _keep_here(secret)
    return blob


def fetch():
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        try:
            _cloud().download(BUCKET, KEY, tmp)
        except Exception as e:                           # noqa: BLE001
            said = str(e).lower()
            if "404" in said or "not found" in said or "not_found" in said:
                raise RuntimeError("nobody has set up the lab's key for Hater of AI yet "
                                   "(tools/floss_setup.py)")
            raise
        with open(tmp, "rb") as fh:
            return json.loads(base64.b64decode(fh.read()).decode())
    finally:
        os.remove(tmp)


def unlock(pin):
    """A new machine: the PIN opens the shared copy, which is then kept here."""
    with _TRIES_LOCK:
        wait = _TRIES["until"] - time.time()
        if wait > 0:
            raise WrongPin("too many wrong PINs; try again in %d min"
                           % (int(wait) // 60 + 1))
    blob = fetch()
    try:
        secret = open_sealed(blob, pin)
    except WrongPin:
        with _TRIES_LOCK:
            _TRIES["wrong"] += 1
            if _TRIES["wrong"] >= sm.MAX_WRONG:
                _TRIES.update(wrong=0, until=time.time() + sm.WAIT_S)
        raise
    with _TRIES_LOCK:
        _TRIES["wrong"] = 0
    _keep_here(secret)
    return kind_of(secret)
