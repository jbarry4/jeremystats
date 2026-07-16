# Solid or Sputter — web (Vercel)

A pure client-side image sorter. Opens a folder on your computer, makes
`Solid / Sputter / Garbage / Flag` subfolders, and copies each image into the
category you pick (originals stay in the main folder). Everything runs in the
browser — no server, no upload, nothing leaves your machine.

**Requires Chrome or Edge (desktop)** — it uses the File System Access API.

## Deploy to Vercel

This is a static site (just `index.html`). Any of these work:

**Option A — Vercel CLI**
```bash
npm i -g vercel
cd vercel-solid-or-sputter
vercel            # first run: link/create the project
vercel --prod     # promote to production
```

**Option B — Git**
Push this folder to a GitHub repo, then "Import Project" on vercel.com and
point the Root Directory at `vercel-solid-or-sputter`. No build step
(Framework Preset: **Other**, Build Command: none, Output Directory: `.`).

**Option C — drag & drop**
Drag this folder onto https://vercel.com/new.

## Important: this does NOT sort files on the VACC

A browser (whether local or hosted on Vercel) cannot SSH into VACC, and
Vercel's stateless serverless functions cannot hold an SSH/SFTP session or
handle Duo 2FA per request. This app only sorts folders on the computer
running the browser.

To sort files **on the VACC**, use one of:

1. **Map the storage as a drive** (Netfiles/Research Storage as a network
   drive, or SFTP-mount via WinFsp + SSHFS-Win), then open that drive here.
2. **Run the Python server on VACC** (`Solid or Sputter Web.py`) over an SSH
   tunnel, so the sorting happens on the cluster:
   ```bash
   # in one terminal — log in and forward the port
   ssh -L 5000:localhost:5000 <netid>@login.vacc.uvm.edu
   # then on VACC:
   pip install --user flask paramiko
   python "Solid or Sputter Web.py"     # local mode there = the cluster's filesystem
   # on your PC, open http://localhost:5000
   ```
3. **VACC Open OnDemand**, if enabled for your account — use its file browser
   or host the Flask app as an interactive app.
