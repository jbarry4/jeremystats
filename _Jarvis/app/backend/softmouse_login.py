"""
softmouse_login.py -- the lab's SoftMouse sign-in, so Jarvis can sign itself in.

SoftMouse is one lab account (username + password, no Duo), and its session
dies on its own. Without this, every lapsed session waits for whoever knows
the password. With it, anyone whose Jarvis has the cloud sync can sync.

WHERE IT LIVES, AND WHY THERE

    The shared copy   Supabase storage, bucket "results" (private; only a
                      machine with the lab's key can fetch it), object
                      jarvis-secrets/softmouse-login.txt -- encrypted with a
                      PIN. NOT the repo: jbarry4/jeremystats is public, and a
                      five-digit PIN is a lock on a cupboard, not on a safe.
    This machine's    %LOCALAPPDATA%\\Jarvis\\softmouse\\login.bin, sealed with
                      Windows DPAPI: only this Windows user on this machine
                      can open it. Written once, when someone types the PIN.

THE PIN unlocks the shared copy on a new machine, once. It is stretched with
scrypt (256 MiB, about a second a guess) so that a guess costs something;
with only 100,000 PINs that slows someone holding the lab's key down, it does
not stop them. The real gate is the key. The hint ships beside the PIN check.

THE CIPHER is stdlib only (colleagues' Pythons may lack `cryptography`):
scrypt -> 64 bytes, split into an encryption and a MAC key; HMAC-SHA256 in
counter mode as the keystream; HMAC-SHA256 over everything as the tag,
checked before anything is decrypted.
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time

from .paths import LOGS_DIR

BUCKET = "results"
KEY = "jarvis-secrets/softmouse-login.txt"
HINT = "2 funny numbers"
SCRYPT = {"n": 2 ** 18, "r": 8, "p": 1}
_MAXMEM = 512 * 1024 * 1024

_STATE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                      "Jarvis", "softmouse")
LOCAL = os.path.join(_STATE, "login.bin")

# Wrong PINs: five, then a five-minute wait. Per process; scrypt is the rest.
_TRIES = {"wrong": 0, "until": 0.0}
_TRIES_LOCK = threading.Lock()
MAX_WRONG, WAIT_S = 5, 300


class WrongPin(ValueError):
    pass


# --- the cipher -----------------------------------------------------------------

def _keys(pin, salt, kdf):
    k = hashlib.scrypt(str(pin).encode(), salt=salt, n=kdf["n"], r=kdf["r"],
                       p=kdf["p"], maxmem=_MAXMEM, dklen=64)
    return k[:32], k[32:]


def _stream(key, nonce, n):
    out, i = bytearray(), 0
    while len(out) < n:
        out += hmac.new(key, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
        i += 1
    return bytes(out[:n])


def _mac(key, nonce, ct):
    return hmac.new(key, b"jarvis-softmouse-v1" + nonce + ct, hashlib.sha256).digest()


def seal(username, password, pin, by=None):
    salt, nonce = os.urandom(16), os.urandom(16)
    ek, mk = _keys(pin, salt, SCRYPT)
    pt = json.dumps({"username": username, "password": password}).encode()
    ct = bytes(a ^ b for a, b in zip(pt, _stream(ek, nonce, len(pt))))
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 1, "what": "SoftMouse sign-in for Jarvis", "hint": HINT,
            "kdf": dict(SCRYPT, name="scrypt"), "salt": b64(salt), "nonce": b64(nonce),
            "ct": b64(ct), "tag": b64(_mac(mk, nonce, ct)),
            "by": by, "at": time.strftime("%Y-%m-%d %H:%M")}


def open_sealed(blob, pin):
    d = lambda k: base64.b64decode(blob[k])
    salt, nonce, ct = d("salt"), d("nonce"), d("ct")
    ek, mk = _keys(pin, salt, blob["kdf"])
    if not hmac.compare_digest(_mac(mk, nonce, ct), d("tag")):
        raise WrongPin("that PIN does not open it")
    pt = bytes(a ^ b for a, b in zip(ct, _stream(ek, nonce, len(ct))))
    got = json.loads(pt.decode())
    return got["username"], got["password"]


# --- this machine: DPAPI --------------------------------------------------------

class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data, protect):
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    src, dst = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(dst)):
        raise OSError("Windows could not %s the saved sign-in"
                      % ("seal" if protect else "open"))
    try:
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        kernel32.LocalFree(dst.pbData)


def _keep_here(username, password):
    os.makedirs(_STATE, exist_ok=True)
    sealed = _dpapi(json.dumps({"username": username, "password": password}).encode(), True)
    fd, tmp = tempfile.mkstemp(dir=_STATE, suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(sealed)
    os.replace(tmp, LOCAL)


def here():
    """(username, password) on this machine, or None."""
    try:
        with open(LOCAL, "rb") as fh:
            got = json.loads(_dpapi(fh.read(), False).decode())
        return got["username"], got["password"]
    except (OSError, ValueError, KeyError):
        return None


def forget_here():
    try:
        os.remove(LOCAL)
    except FileNotFoundError:
        pass


# --- the shared copy ------------------------------------------------------------

def _cloud():
    from . import cloud
    c = cloud.Cloud(LOGS_DIR)
    if not c.configured:
        raise RuntimeError("this Jarvis has no cloud sync, so it cannot fetch the "
                           "lab's SoftMouse sign-in. Use Sign in instead")
    return c


def publish(username, password, pin, by=None):
    """The one-time lab set-up: seal with the PIN, put it in the bucket, and
    keep it on this machine too."""
    blob = seal(username, password, pin, by=by)
    if open_sealed(blob, pin) != (username, password):
        raise RuntimeError("the sealed copy did not open again; nothing was sent")
    # As base64 text: Cloud._call hands back any body that parses as JSON as
    # JSON, and download() then refuses it as "not a file".
    fd, tmp = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(base64.b64encode(json.dumps(blob).encode()))
        _cloud().upload(BUCKET, KEY, tmp, content_type="text/plain")
    finally:
        os.remove(tmp)
    _keep_here(username, password)
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
                raise RuntimeError("nobody has set up the lab's SoftMouse sign-in "
                                   "yet. Use Sign in instead")
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
        username, password = open_sealed(blob, pin)
    except WrongPin:
        with _TRIES_LOCK:
            _TRIES["wrong"] += 1
            if _TRIES["wrong"] >= MAX_WRONG:
                _TRIES.update(wrong=0, until=time.time() + WAIT_S)
        raise
    with _TRIES_LOCK:
        _TRIES["wrong"] = 0
    _keep_here(username, password)
    return username
