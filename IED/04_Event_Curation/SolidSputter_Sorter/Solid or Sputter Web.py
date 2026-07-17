#!/usr/bin/env python3
# Solid or Sputter Web.py
#
# Browser-based version of "Solid or Sputter".
# Run:   python "Solid or Sputter Web.py"
# Open:  http://localhost:5000
#
# Two modes:
#   * Local  -> sorts image folders on THIS machine (the one running the server).
#   * VACC   -> logs in to login.vacc.uvm.edu with your NetID over SSH/SFTP,
#               lets you browse remote folders and sorts them ON THE CLUSTER.
#               (Only thumbnails stream to the browser; the actual copy/move
#                happens server-side on VACC, so image data stays on VACC.)
#
# Sorting behavior matches the desktop app: originals stay in the main folder,
# and a COPY is placed in a Solid/Sputter/Garbage/Flag subfolder.

import io
import os
import re
import stat
import shlex
import shutil
import posixpath
import threading
import mimetypes
import secrets

from flask import Flask, request, jsonify, send_file, render_template_string, abort

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except Exception:
    PARAMIKO_AVAILABLE = False

APP_TITLE = "Solid or Sputter"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".jfif"}
CATEGORIES = ["Solid", "Sputter", "Garbage", "Flag"]
VACC_HOST = "login.vacc.uvm.edu"
VACC_PORT = 22

app = Flask(__name__)

# token -> Session
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()


def natural_key(name: str):
    stem = os.path.splitext(name)[0]
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", stem)]


# ----------------------------------------------------------------------------
# Filesystem backends
# ----------------------------------------------------------------------------

class LocalBackend:
    """Operates on the filesystem of the machine running the server."""
    kind = "local"

    def home(self):
        return os.path.expanduser("~")

    def join(self, d, name):
        return os.path.join(d, name)

    def dirname(self, p):
        return os.path.dirname(p)

    def basename(self, p):
        return os.path.basename(p)

    def parent(self, p):
        par = os.path.dirname(os.path.normpath(p))
        return par if par and par != p else p

    def exists(self, p):
        return os.path.exists(p)

    def makedirs(self, p):
        os.makedirs(p, exist_ok=True)

    def listdir(self, p):
        """Return (dirs, files) lists of names."""
        dirs, files = [], []
        for name in os.listdir(p):
            full = os.path.join(p, name)
            try:
                if os.path.isdir(full):
                    dirs.append(name)
                else:
                    files.append(name)
            except OSError:
                pass
        return dirs, files

    def copy(self, src, dst):
        shutil.copy2(src, dst)

    def move(self, src, dst):
        shutil.move(src, dst)

    def delete(self, p):
        if os.path.exists(p):
            os.remove(p)

    def read_bytes(self, p):
        with open(p, "rb") as f:
            return f.read()

    def close(self):
        pass


class VaccBackend:
    """Operates on the VACC cluster over SSH/SFTP.

    File listing/reading uses SFTP. Copy/move/delete/mkdir run as real shell
    commands ON the cluster (cp -p / mv / rm / mkdir -p) so the sorting happens
    entirely within VACC and no image data is round-tripped through the browser.
    """
    kind = "vacc"

    def __init__(self, client):
        self.client = client
        self.sftp = client.open_sftp()

    # -- shell helpers -------------------------------------------------------
    def _run(self, cmd):
        stdin, stdout, stderr = self.client.exec_command(cmd)
        rc = stdout.channel.recv_exit_status()
        err = stderr.read().decode("utf-8", "replace")
        if rc != 0:
            raise RuntimeError(err.strip() or f"remote command failed (rc={rc})")

    def home(self):
        try:
            return self.sftp.normalize(".")
        except Exception:
            return "/"

    def join(self, d, name):
        return posixpath.join(d, name)

    def dirname(self, p):
        return posixpath.dirname(p)

    def basename(self, p):
        return posixpath.basename(p)

    def parent(self, p):
        par = posixpath.dirname(p.rstrip("/")) or "/"
        return par

    def exists(self, p):
        try:
            self.sftp.stat(p)
            return True
        except IOError:
            return False

    def makedirs(self, p):
        self._run(f"mkdir -p -- {shlex.quote(p)}")

    def listdir(self, p):
        dirs, files = [], []
        for attr in self.sftp.listdir_attr(p):
            if stat.S_ISDIR(attr.st_mode):
                dirs.append(attr.filename)
            else:
                files.append(attr.filename)
        return dirs, files

    def copy(self, src, dst):
        self._run(f"cp -p -- {shlex.quote(src)} {shlex.quote(dst)}")

    def move(self, src, dst):
        self._run(f"mv -- {shlex.quote(src)} {shlex.quote(dst)}")

    def delete(self, p):
        self._run(f"rm -f -- {shlex.quote(p)}")

    def read_bytes(self, p):
        with self.sftp.open(p, "rb") as f:
            f.prefetch()
            return f.read()

    def close(self):
        try:
            self.sftp.close()
        except Exception:
            pass
        try:
            self.client.close()
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Session (folder + entries + history) — mirrors the desktop app's model
# ----------------------------------------------------------------------------

class Session:
    def __init__(self, backend):
        self.backend = backend
        self.lock = threading.Lock()
        self.folder = None
        self.entries = []   # {orig_name, orig_path, label, copy_path}
        self.index = 0
        self.history = []

    # -- folder scan ---------------------------------------------------------
    def open_folder(self, folder):
        b = self.backend
        if not b.exists(folder):
            raise FileNotFoundError("Folder not found.")
        for cat in CATEGORIES:
            b.makedirs(b.join(folder, cat))

        dirs, files = b.listdir(folder)
        originals = [n for n in files if os.path.splitext(n)[1].lower() in IMAGE_EXTS]
        originals.sort(key=natural_key)

        entries = []
        for name in originals:
            label, copy_path = self._detect_label(folder, name)
            entries.append({
                "orig_name": name,
                "orig_path": b.join(folder, name),
                "label": label,
                "copy_path": copy_path,
            })

        self.folder = folder
        self.entries = entries
        self.index = 0
        self.history = []

    def _detect_label(self, folder, name):
        b = self.backend
        for cat in CATEGORIES:
            p = b.join(b.join(folder, cat), name)
            if b.exists(p):
                return cat, p
        return None, None

    def _unique_dest(self, folder_cat, name):
        b = self.backend
        candidate = b.join(folder_cat, name)
        if not b.exists(candidate):
            return candidate
        stem, suffix = os.path.splitext(name)
        i = 1
        while True:
            trial = b.join(folder_cat, f"{stem} ({i}){suffix}")
            if not b.exists(trial):
                return trial
            i += 1

    # -- labeling ------------------------------------------------------------
    def apply_label(self, new_label):
        if not self.entries:
            return
        e = self.entries[self.index]
        b = self.backend
        prev_label, prev_copy = e["label"], e["copy_path"]

        if prev_label == new_label:
            self._advance()
            return

        cat_dir = b.join(self.folder, new_label)
        target = self._unique_dest(cat_dir, e["orig_name"])

        if prev_label is None:
            b.copy(e["orig_path"], target)
            action = "copy_create"
        else:
            b.move(prev_copy, target)
            action = "copy_move"

        e["label"] = new_label
        e["copy_path"] = target
        self.history.append({
            "action": action, "idx": self.index,
            "prev_label": prev_label, "prev_copy_path": prev_copy,
            "new_label": new_label, "new_copy_path": target,
        })
        self._advance()

    def clear_label(self):
        if not self.entries:
            return
        e = self.entries[self.index]
        if e["label"] is None:
            return
        b = self.backend
        prev_label, prev_copy = e["label"], e["copy_path"]
        if prev_copy:
            b.delete(prev_copy)
        e["label"] = None
        e["copy_path"] = None
        self.history.append({
            "action": "copy_delete", "idx": self.index,
            "prev_label": prev_label, "prev_copy_path": prev_copy,
            "new_label": None, "new_copy_path": None,
        })
        # no auto-advance on clear (matches desktop app)

    def undo(self):
        if not self.history:
            return
        h = self.history.pop()
        e = self.entries[h["idx"]]
        b = self.backend
        act = h["action"]
        if act == "copy_create":
            if h["new_copy_path"]:
                b.delete(h["new_copy_path"])
            e["label"] = h["prev_label"]
            e["copy_path"] = h["prev_copy_path"]
        elif act == "copy_move":
            dst = h["prev_copy_path"] or self._unique_dest(
                b.join(self.folder, h["prev_label"]), e["orig_name"])
            dst = self._unique_dest(b.dirname(dst), b.basename(dst))
            b.move(h["new_copy_path"], dst)
            e["label"] = h["prev_label"]
            e["copy_path"] = dst
        elif act == "copy_delete":
            dst = h["prev_copy_path"] or b.join(
                b.join(self.folder, h["prev_label"]), e["orig_name"])
            dst = self._unique_dest(b.dirname(dst), b.basename(dst))
            b.copy(e["orig_path"], dst)
            e["label"] = h["prev_label"]
            e["copy_path"] = dst
        self.index = h["idx"]

    # -- navigation ----------------------------------------------------------
    def _advance(self):
        if self.entries:
            self.index = (self.index + 1) % len(self.entries)

    def nav(self, delta):
        if self.entries:
            self.index = (self.index + delta) % len(self.entries)

    def goto(self, idx):
        if self.entries and 0 <= idx < len(self.entries):
            self.index = idx

    # -- state for the UI ----------------------------------------------------
    def state(self):
        counts = {c: 0 for c in CATEGORIES}
        labeled = 0
        for e in self.entries:
            if e["label"] in CATEGORIES:
                labeled += 1
                counts[e["label"]] += 1
        cur = self.entries[self.index] if self.entries else None
        return {
            "folder": self.folder,
            "total": len(self.entries),
            "index": self.index,
            "labeled": labeled,
            "counts": counts,
            "can_undo": bool(self.history),
            "name": cur["orig_name"] if cur else None,
            "label": cur["label"] if cur else None,
        }


# ----------------------------------------------------------------------------
# Session helpers
# ----------------------------------------------------------------------------

def new_session(backend):
    token = secrets.token_urlsafe(16)
    sess = Session(backend)
    with SESSIONS_LOCK:
        SESSIONS[token] = sess
    return token, sess


def get_session():
    token = (request.get_json(silent=True) or {}).get("token") or request.args.get("token")
    with SESSIONS_LOCK:
        sess = SESSIONS.get(token)
    if sess is None:
        abort(410, "Session expired or not found. Please reconnect.")
    return sess


def connect_vacc(netid, password, duo):
    """Open an SSH connection to VACC, handling password + Duo 2FA.

    Duo: UVM SSH logins typically prompt for a second factor. `duo` may be a
    6-digit passcode, or 'push'/'1' to send a Duo push to your phone.
    """
    if not PARAMIKO_AVAILABLE:
        raise RuntimeError("paramiko is not installed. Run: pip install paramiko")

    transport = paramiko.Transport((VACC_HOST, VACC_PORT))
    transport.start_client(timeout=25)

    duo_answer = (duo or "1").strip()  # default: Duo push (option 1)

    def interactive_handler(title, instructions, prompt_list):
        answers = []
        for prompt, echo in prompt_list:
            p = (prompt or "").lower()
            if "password" in p:
                answers.append(password)
            else:
                # passcode / duo / "enter a passcode or select an option" etc.
                answers.append(duo_answer)
        return answers

    # 1) Try plain password auth first.
    try:
        transport.auth_password(netid, password)
    except paramiko.ssh_exception.BadAuthenticationType:
        pass
    except paramiko.ssh_exception.PartialAuthentication:
        pass
    except paramiko.AuthenticationException:
        # Some setups go straight to keyboard-interactive.
        pass

    # 2) If not yet authenticated, complete with keyboard-interactive (Duo).
    if not transport.is_authenticated():
        try:
            transport.auth_interactive(netid, interactive_handler)
        except paramiko.ssh_exception.PartialAuthentication:
            transport.auth_interactive(netid, interactive_handler)

    if not transport.is_authenticated():
        transport.close()
        raise RuntimeError("Authentication failed (check NetID / password / Duo).")

    client = paramiko.SSHClient()
    client._transport = transport  # reuse the authenticated transport
    return VaccBackend(client)


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(PAGE, paramiko_available=PARAMIKO_AVAILABLE)


@app.post("/api/session/local")
def api_session_local():
    backend = LocalBackend()
    token, sess = new_session(backend)
    return jsonify({"token": token, "start": backend.home()})


@app.post("/api/session/vacc")
def api_session_vacc():
    data = request.get_json(force=True)
    netid = (data.get("netid") or "").strip()
    password = data.get("password") or ""
    duo = data.get("duo") or ""
    if not netid or not password:
        return jsonify({"error": "NetID and password are required."}), 400
    try:
        backend = connect_vacc(netid, password, duo)
    except Exception as e:
        return jsonify({"error": str(e)}), 401
    token, sess = new_session(backend)
    return jsonify({"token": token, "start": backend.home()})


@app.post("/api/browse")
def api_browse():
    sess = get_session()
    data = request.get_json(force=True)
    path = data.get("path") or sess.backend.home()
    b = sess.backend
    try:
        with sess.lock:
            dirs, files = b.listdir(path)
    except Exception as e:
        return jsonify({"error": f"Cannot open: {e}"}), 400
    img_count = sum(1 for f in files if os.path.splitext(f)[1].lower() in IMAGE_EXTS)
    dirs = [d for d in dirs if not d.startswith(".")]
    dirs.sort(key=natural_key)
    return jsonify({
        "path": path,
        "parent": b.parent(path),
        "dirs": dirs,
        "image_count": img_count,
        "sep": "/" if b.kind == "vacc" else os.sep,
    })


@app.post("/api/open")
def api_open():
    sess = get_session()
    data = request.get_json(force=True)
    path = data.get("path")
    try:
        with sess.lock:
            sess.open_folder(path)
            st = sess.state()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(st)


@app.post("/api/label")
def api_label():
    sess = get_session()
    data = request.get_json(force=True)
    label = data.get("label")
    if label not in CATEGORIES:
        return jsonify({"error": "bad label"}), 400
    try:
        with sess.lock:
            sess.apply_label(label)
            st = sess.state()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(st)


@app.post("/api/clear")
def api_clear():
    sess = get_session()
    try:
        with sess.lock:
            sess.clear_label()
            st = sess.state()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(st)


@app.post("/api/undo")
def api_undo():
    sess = get_session()
    try:
        with sess.lock:
            sess.undo()
            st = sess.state()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(st)


@app.post("/api/nav")
def api_nav():
    sess = get_session()
    data = request.get_json(force=True)
    with sess.lock:
        if "goto" in data:
            sess.goto(int(data["goto"]))
        else:
            sess.nav(int(data.get("delta", 1)))
        st = sess.state()
    return jsonify(st)


@app.get("/api/image")
def api_image():
    sess = get_session()
    try:
        idx = int(request.args.get("index", sess.index))
    except ValueError:
        idx = sess.index
    with sess.lock:
        if not sess.entries or not (0 <= idx < len(sess.entries)):
            abort(404)
        path = sess.entries[idx]["orig_path"]
        name = sess.entries[idx]["orig_name"]
        try:
            data = sess.backend.read_bytes(path)
        except Exception:
            abort(404)
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    resp = send_file(io.BytesIO(data), mimetype=ctype, download_name=name)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/api/close")
def api_close():
    token = (request.get_json(silent=True) or {}).get("token")
    with SESSIONS_LOCK:
        sess = SESSIONS.pop(token, None)
    if sess:
        try:
            sess.backend.close()
        except Exception:
            pass
    return jsonify({"ok": True})


# ----------------------------------------------------------------------------
# Front-end (single page)
# ----------------------------------------------------------------------------

PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solid or Sputter</title>
<style>
  :root{
    --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --border:#2a2f3a;
    --text:#e7e9ee; --muted:#9aa3b2; --accent:#4f8cff;
    --solid:#2aa198; --sputter:#b58900; --garbage:#dc322f; --flag:#6c71c4;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font-family:"Segoe UI",system-ui,Arial,sans-serif}
  button{font-family:inherit;cursor:pointer}
  .hidden{display:none!important}

  header{display:flex;align-items:center;gap:12px;padding:10px 16px;
         background:var(--panel);border-bottom:1px solid var(--border)}
  header h1{font-size:18px;margin:0;font-weight:700}
  header .mode{font-size:12px;color:var(--muted);padding:2px 8px;border:1px solid var(--border);border-radius:999px}
  header .spacer{flex:1}
  .btn{background:var(--panel2);color:var(--text);border:1px solid var(--border);
       border-radius:8px;padding:8px 12px;font-size:13px}
  .btn:hover{border-color:var(--accent)}
  .btn:disabled{opacity:.4;cursor:not-allowed}
  .btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}

  /* landing / dialogs */
  .center{min-height:calc(100vh - 52px);display:flex;align-items:center;justify-content:center;padding:20px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:14px;
        padding:24px;width:100%;max-width:460px}
  .card h2{margin:0 0 6px}
  .card p{color:var(--muted);margin:0 0 18px;font-size:14px;line-height:1.5}
  .field{margin-bottom:12px}
  .field label{display:block;font-size:12px;color:var(--muted);margin-bottom:4px}
  .field input{width:100%;padding:10px;background:var(--panel2);border:1px solid var(--border);
               border-radius:8px;color:var(--text);font-size:14px}
  .row{display:flex;gap:10px}
  .row>*{flex:1}
  .err{color:var(--garbage);font-size:13px;margin-top:8px;min-height:16px}
  .hint{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.5}

  /* folder browser */
  .browser{max-width:640px}
  .crumb{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--muted);
         background:var(--panel2);border:1px solid var(--border);border-radius:8px;
         padding:8px 10px;margin-bottom:10px;word-break:break-all}
  .dirlist{max-height:46vh;overflow:auto;border:1px solid var(--border);border-radius:8px;background:var(--panel2)}
  .diritem{padding:9px 12px;border-bottom:1px solid var(--border);font-size:14px;display:flex;gap:8px;align-items:center}
  .diritem:hover{background:#242a35;cursor:pointer}
  .diritem:last-child{border-bottom:none}
  .diritem .ico{opacity:.8}
  .imgcount{color:var(--accent);font-size:13px;margin:10px 0}

  /* viewer */
  #viewer{display:flex;flex-direction:column;height:calc(100vh - 52px)}
  .stage{flex:1;position:relative;background:#0a0c10;overflow:hidden;user-select:none}
  .stage img{position:absolute;top:0;left:0;width:100%;height:100%;object-fit:contain;
             transform-origin:center center;will-change:transform}
  .overlay{position:absolute;pointer-events:none;font-size:13px}
  .badge{top:12px;right:12px;background:rgba(0,0,0,.55);padding:6px 12px;border-radius:8px;font-weight:700}
  .fname{left:12px;bottom:10px;background:rgba(0,0,0,.55);padding:4px 10px;border-radius:8px}
  .counter{right:12px;bottom:10px;background:rgba(0,0,0,.55);padding:4px 10px;border-radius:8px;color:#fff}
  .zoombar{position:absolute;left:12px;top:12px;display:flex;gap:6px;pointer-events:auto}
  .zoombar .btn{padding:5px 9px;font-size:12px}
  .progresswrap{padding:8px 16px;background:var(--panel);border-top:1px solid var(--border);
                display:flex;align-items:center;gap:14px}
  .bar{flex:1;height:8px;background:var(--panel2);border-radius:999px;overflow:hidden}
  .bar>div{height:100%;background:var(--accent);width:0}
  .counts{font-size:12px;color:var(--muted);white-space:nowrap}
  .actions{display:flex;gap:8px;padding:10px 16px;background:var(--panel);flex-wrap:wrap;justify-content:center}
  .lbl-solid{border-color:var(--solid)} .lbl-sputter{border-color:var(--sputter)}
  .lbl-garbage{border-color:var(--garbage)} .lbl-flag{border-color:var(--flag)}
  .help{font-size:11px;color:var(--muted);text-align:center;padding:0 16px 10px}
</style>
</head>
<body>
<header>
  <h1>Solid or Sputter</h1>
  <span class="mode" id="modeChip"></span>
  <div class="spacer"></div>
  <button class="btn hidden" id="switchBtn">Switch folder</button>
  <button class="btn hidden" id="quitBtn">Start over</button>
</header>

<!-- LANDING -->
<div class="center" id="landing">
  <div class="card">
    <h2>Choose a source</h2>
    <p>Sort image folders into <b>Solid</b>, <b>Sputter</b>, <b>Garbage</b>, and <b>Flag</b>.
       Originals stay put; a copy goes into each category subfolder.</p>
    <div class="field"><button class="btn primary" style="width:100%" id="chooseLocal">💻 &nbsp;Local folder (this computer)</button></div>
    <div class="field"><button class="btn" style="width:100%" id="chooseVacc">🔗 &nbsp;Connect to VACC (NetID)</button></div>
    <div class="hint" id="paramikoHint"></div>
  </div>
</div>

<!-- VACC LOGIN -->
<div class="center hidden" id="vaccLogin">
  <div class="card">
    <h2>Connect to VACC</h2>
    <p>Logs in to <b>login.vacc.uvm.edu</b> over SSH. Sorting happens on the cluster.</p>
    <div class="field"><label>NetID</label><input id="vNetid" autocomplete="username"></div>
    <div class="field"><label>UVM password</label><input id="vPass" type="password" autocomplete="current-password"></div>
    <div class="field"><label>Duo 2FA — passcode, or "push" for a phone push</label><input id="vDuo" placeholder="push"></div>
    <div class="row">
      <button class="btn" id="vBack">Back</button>
      <button class="btn primary" id="vConnect">Connect</button>
    </div>
    <div class="err" id="vErr"></div>
    <div class="hint">Your credentials are sent only to this local server, which forwards them to VACC. They are not stored.</div>
  </div>
</div>

<!-- FOLDER BROWSER -->
<div class="center hidden" id="browse">
  <div class="card browser">
    <h2>Pick a folder</h2>
    <div class="crumb" id="crumb"></div>
    <div class="imgcount" id="imgCount"></div>
    <div class="dirlist" id="dirList"></div>
    <div class="row" style="margin-top:14px">
      <button class="btn" id="bUp">⬆ Up</button>
      <button class="btn primary" id="bOpen">Open this folder</button>
    </div>
    <div class="err" id="bErr"></div>
  </div>
</div>

<!-- VIEWER -->
<div id="viewer" class="hidden">
  <div class="stage" id="stage">
    <img id="img" alt="">
    <div class="zoombar">
      <button class="btn" id="zOut">−</button>
      <button class="btn" id="zFit">Fit</button>
      <button class="btn" id="zIn">+</button>
      <span class="badge overlay" style="position:static;background:none;padding:0;color:var(--muted)" id="zPct">100%</span>
    </div>
    <div class="overlay badge" id="badge">Unlabeled</div>
    <div class="overlay fname" id="fname"></div>
    <div class="overlay counter" id="counter"></div>
  </div>
  <div class="progresswrap">
    <div class="bar"><div id="barFill"></div></div>
    <div class="counts" id="counts"></div>
  </div>
  <div class="actions">
    <button class="btn lbl-solid"   data-label="Solid">Solid [1]</button>
    <button class="btn lbl-sputter" data-label="Sputter">Sputter [2]</button>
    <button class="btn lbl-garbage" data-label="Garbage">Garbage [3]</button>
    <button class="btn lbl-flag"    data-label="Flag">Flag [4/F]</button>
    <button class="btn" id="aClear">Clear [C]</button>
    <button class="btn" id="aUndo">Undo [Z]</button>
    <button class="btn" id="aPrev">◀ Prev [←]</button>
    <button class="btn" id="aNext">Next [→] ▶</button>
  </div>
  <div class="help">Solid: keep • Sputter: imperfect • Garbage: discard • Flag: review • Clear removes the copy (original stays). Auto-advances after labeling. Wheel = zoom, drag = pan, double-click/0 = fit.</div>
</div>

<script>
const PARAMIKO = {{ 'true' if paramiko_available else 'false' }};
let token = null, mode = null, browsePath = null;
const BADGE_COLORS = {Solid:"var(--solid)",Sputter:"var(--sputter)",Garbage:"var(--garbage)",Flag:"var(--flag)",null:"var(--muted)"};

const $ = id => document.getElementById(id);
async function api(path, body){
  const r = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json"},
                              body: JSON.stringify(body||{})});
  const data = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(data.error || ("HTTP "+r.status));
  return data;
}
function show(id){ ["landing","vaccLogin","browse","viewer"].forEach(x=>$(x).classList.toggle("hidden", x!==id)); }

// ---- landing ----
$("paramikoHint").textContent = PARAMIKO ? "" : "VACC mode needs the 'paramiko' package (pip install paramiko).";
$("chooseVacc").disabled = !PARAMIKO;
$("chooseLocal").onclick = async () => {
  const d = await api("/api/session/local");
  token = d.token; mode = "local"; $("modeChip").textContent = "Local";
  browsePath = d.start; show("browse"); await loadBrowse();
};
$("chooseVacc").onclick = () => { $("vErr").textContent=""; show("vaccLogin"); };

// ---- vacc login ----
$("vBack").onclick = () => show("landing");
$("vConnect").onclick = async () => {
  $("vErr").textContent = "Connecting…";
  $("vConnect").disabled = true;
  try{
    const d = await api("/api/session/vacc", {
      netid:$("vNetid").value, password:$("vPass").value, duo:$("vDuo").value});
    token = d.token; mode = "vacc"; $("modeChip").textContent = "VACC · "+$("vNetid").value;
    browsePath = d.start; $("vErr").textContent=""; show("browse"); await loadBrowse();
  }catch(e){ $("vErr").textContent = e.message; }
  finally{ $("vConnect").disabled = false; }
};

// ---- folder browser ----
async function loadBrowse(){
  $("bErr").textContent = "";
  try{
    const d = await api("/api/browse", {token, path:browsePath});
    browsePath = d.path;
    $("crumb").textContent = d.path;
    $("imgCount").textContent = d.image_count
      ? ("📷 " + d.image_count + " image" + (d.image_count>1?"s":"") + " here — Open this folder to sort them.")
      : "No images directly in this folder — open a subfolder.";
    const list = $("dirList"); list.innerHTML = "";
    if(!d.dirs.length){
      const e = document.createElement("div"); e.className="diritem"; e.style.opacity=".6";
      e.textContent = "(no subfolders)"; list.appendChild(e);
    }
    d.dirs.forEach(name=>{
      const el = document.createElement("div"); el.className="diritem";
      el.innerHTML = '<span class="ico">📁</span>' + name;
      el.onclick = () => { browsePath = d.path.replace(/[\\/]+$/,"") + d.sep + name; loadBrowse(); };
      list.appendChild(el);
    });
    $("bUp").onclick = () => { browsePath = d.parent; loadBrowse(); };
  }catch(e){ $("bErr").textContent = e.message; }
}
$("bOpen").onclick = async () => {
  $("bErr").textContent = "Opening…";
  try{
    const st = await api("/api/open", {token, path:browsePath});
    if(!st.total){ $("bErr").textContent = "No images in this folder."; return; }
    show("viewer"); $("switchBtn").classList.remove("hidden"); $("quitBtn").classList.remove("hidden");
    render(st);
  }catch(e){ $("bErr").textContent = e.message; }
};

// ---- viewer ----
let cur = 0, lastState = null;
function render(st){
  lastState = st; cur = st.index;
  $("img").src = "/api/image?token="+encodeURIComponent(token)+"&index="+st.index+"&_="+Date.now();
  resetView();
  $("badge").textContent = st.label ? st.label : "Unlabeled";
  $("badge").style.color = BADGE_COLORS[st.label] || "var(--muted)";
  $("fname").textContent = st.name || "";
  $("counter").textContent = (st.total?(st.index+1):0) + " / " + st.total;
  const pct = st.total ? (st.labeled/st.total*100) : 0;
  $("barFill").style.width = pct + "%";
  const c = st.counts;
  $("counts").textContent = `Labeled ${st.labeled}/${st.total}  |  Solid:${c.Solid} Sputter:${c.Sputter} Garbage:${c.Garbage} Flag:${c.Flag}`;
  $("aUndo").disabled = !st.can_undo;
}
async function doLabel(label){ render(await api("/api/label", {token, label})); }
async function doClear(){ render(await api("/api/clear", {token})); }
async function doUndo(){ if(lastState && lastState.can_undo) render(await api("/api/undo", {token})); }
async function doNav(delta){ render(await api("/api/nav", {token, delta})); }

document.querySelectorAll(".actions .btn[data-label]").forEach(b=>{
  b.onclick = () => doLabel(b.dataset.label);
});
$("aClear").onclick = doClear;
$("aUndo").onclick = doUndo;
$("aPrev").onclick = () => doNav(-1);
$("aNext").onclick = () => doNav(1);

$("switchBtn").onclick = () => { show("browse"); loadBrowse(); };
$("quitBtn").onclick = async () => {
  await api("/api/close", {token}).catch(()=>{});
  token=null; $("switchBtn").classList.add("hidden"); $("quitBtn").classList.add("hidden");
  $("modeChip").textContent=""; show("landing");
};

// keyboard
document.addEventListener("keydown", e=>{
  if($("viewer").classList.contains("hidden")) return;
  if(["INPUT","TEXTAREA"].includes(document.activeElement.tagName)) return;
  const k = e.key.toLowerCase();
  if(k==="1") doLabel("Solid");
  else if(k==="2") doLabel("Sputter");
  else if(k==="3") doLabel("Garbage");
  else if(k==="4"||k==="f") doLabel("Flag");
  else if(k==="c") doClear();
  else if(k==="z") doUndo();
  else if(e.key==="ArrowLeft") doNav(-1);
  else if(e.key==="ArrowRight") doNav(1);
  else if(k==="0") resetView();
  else if(k==="+"||k==="=") zoomAt(1.1);
  else if(k==="-") zoomAt(0.9);
  else return;
  e.preventDefault();
});

// ---- zoom & pan ----
let scale=1, tx=0, ty=0, MINZ=0.25, MAXZ=8, panning=false, sx=0, sy=0;
function applyTransform(){
  $("img").style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
  $("zPct").textContent = Math.round(scale*100)+"%";
}
function resetView(){ scale=1; tx=0; ty=0; applyTransform(); }
function zoomAt(factor, px, py){
  const stage = $("stage").getBoundingClientRect();
  if(px===undefined){ px = stage.width/2; py = stage.height/2; }
  const cx = px - stage.width/2, cy = py - stage.height/2;   // relative to center
  const ns = Math.min(MAXZ, Math.max(MINZ, scale*factor));
  // keep content point under cursor fixed
  tx = cx - ((cx - tx)/scale)*ns;
  ty = cy - ((cy - ty)/scale)*ns;
  scale = ns; applyTransform();
}
$("zIn").onclick = () => zoomAt(1.1);
$("zOut").onclick = () => zoomAt(0.9);
$("zFit").onclick = resetView;
$("stage").addEventListener("wheel", e=>{
  e.preventDefault();
  const r = $("stage").getBoundingClientRect();
  zoomAt(e.deltaY<0?1.1:0.9, e.clientX-r.left, e.clientY-r.top);
}, {passive:false});
$("stage").addEventListener("mousedown", e=>{ panning=true; sx=e.clientX; sy=e.clientY; });
window.addEventListener("mousemove", e=>{
  if(!panning) return; tx += e.clientX-sx; ty += e.clientY-sy; sx=e.clientX; sy=e.clientY; applyTransform();
});
window.addEventListener("mouseup", ()=>panning=false);
$("stage").addEventListener("dblclick", resetView);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(f"\n  {APP_TITLE} (web) — open  http://localhost:5000  in your browser")
    if not PARAMIKO_AVAILABLE:
        print("  NOTE: 'paramiko' not installed -> VACC mode disabled. Run: pip install paramiko")
    print("  Press Ctrl+C to stop.\n")
    app.run(host="127.0.0.1", port=5000, threaded=True)
