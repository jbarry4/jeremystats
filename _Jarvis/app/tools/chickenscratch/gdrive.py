# -*- coding: utf-8 -*-
"""Google Drive through rclone's sign-in (remote gdrive:, barrylabuvm@gmail.com).

rclone keeps the OAuth token in %APPDATA%\\rclone\\rclone.conf and refreshes it
whenever it runs; this reads it and calls the Drive v3 API directly, which
can do what rclone cannot (export a Sheet as xlsx by id, read revisions).
Read-only by intent: nothing here writes to Drive.
"""
import configparser
import glob
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

CONF = os.path.expandvars(r"%APPDATA%\rclone\rclone.conf")
API = "https://www.googleapis.com/drive/v3"
EXPORT = {
    "application/vnd.google-apps.spreadsheet":
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
}


def rclone_exe():
    hits = glob.glob(os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Rclone.Rclone_*\rclone-*\rclone.exe"))
    if not hits:
        raise RuntimeError("rclone is not installed (winget install Rclone.Rclone)")
    return hits[0]


_TOK = {"t": None, "exp": 0}


def token():
    if _TOK["t"] and time.time() < _TOK["exp"] - 120:
        return _TOK["t"]
    c = configparser.ConfigParser()
    c.read(CONF)
    tok = json.loads(c["gdrive"]["token"])
    exp = time.mktime(time.strptime(tok["expiry"][:19], "%Y-%m-%dT%H:%M:%S"))
    if exp - time.time() < 300:
        # Any rclone call refreshes and rewrites the token.
        subprocess.run([rclone_exe(), "about", "gdrive:", "-q"], capture_output=True)
        c = configparser.ConfigParser()
        c.read(CONF)
        tok = json.loads(c["gdrive"]["token"])
        exp = time.mktime(time.strptime(tok["expiry"][:19], "%Y-%m-%dT%H:%M:%S"))
    _TOK.update(t=tok["access_token"], exp=exp)
    return _TOK["t"]


def get(path, params=None, raw=False, tries=7):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for i in range(tries):
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token()})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                body = r.read()
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) or (e.code == 403 and b"rate" in e.read().lower()):
                time.sleep(2 ** i)
                continue
            raise
    raise RuntimeError("Drive kept refusing " + path)


FIELDS = ("nextPageToken, files(id, name, mimeType, parents, modifiedTime, createdTime, "
          "size, owners(emailAddress, displayName), lastModifyingUser(displayName), "
          "shortcutDetails, webViewLink, driveId)")


def list_all(q="trashed = false"):
    out, page = [], None
    while True:
        p = {"q": q, "fields": FIELDS, "pageSize": 1000, "corpora": "allDrives",
             "includeItemsFromAllDrives": "true", "supportsAllDrives": "true"}
        if page:
            p["pageToken"] = page
        d = get("/files", p)
        out += d.get("files", [])
        page = d.get("nextPageToken")
        if not page:
            return out


def download(f, dest_dir):
    """A file to dest_dir/<id><ext>; Google-native files are exported."""
    os.makedirs(dest_dir, exist_ok=True)
    mt = f["mimeType"]
    if mt in EXPORT:
        emt, ext = EXPORT[mt]
        dest = os.path.join(dest_dir, f["id"] + ext)
        if not os.path.exists(dest):
            body = get("/files/%s/export" % f["id"], {"mimeType": emt}, raw=True)
            with open(dest, "wb") as fh:
                fh.write(body)
        return dest
    ext = os.path.splitext(f["name"])[1].lower() or ".bin"
    dest = os.path.join(dest_dir, f["id"] + ext)
    if not os.path.exists(dest):
        body = get("/files/%s" % f["id"], {"alt": "media", "supportsAllDrives": "true"}, raw=True)
        with open(dest, "wb") as fh:
            fh.write(body)
    return dest
