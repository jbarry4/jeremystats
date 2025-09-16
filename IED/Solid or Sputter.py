#!/usr/bin/env python3
# solid_or_sputter.py
#Hi Hunter

import os
import sys
import shutil
from pathlib import Path
from functools import partial

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD   # optional, for drag-and-drop
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

APP_TITLE = "Solid or Sputter"
INSTRUCTIONS = "Welcome! Drop it like it's hot…\nDrop a folder here or click Open Folder."
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".jfif"}
CATEGORIES = ["Solid", "Sputter", "Garbage", "Flag"]
CANVAS_W, CANVAS_H = 1000, 700

def natural_key(p: Path):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.stem)]

class SolidOrSputterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1120x980")
        self.root.minsize(920, 820)

        # --- state ---
        self.folder: Path | None = None
        # entries: [{orig_name, root, orig_path, label, copy_path, pil}]
        self.entries = []
        self.index = 0
        self.tk_img = None
        # history items: dict(action, idx, prev_label, prev_copy_path, new_label, new_copy_path)
        self.history = []

        # zoom/pan state
        self.base_fit_scale = 1.0
        self.zoom = 1.0
        self.min_zoom = 0.25
        self.max_zoom = 8.0
        self.pan_x = 0
        self.pan_y = 0
        self.panning = False
        self.pan_start = (0, 0)

        # --- header ---
        header = ttk.Frame(root, padding=(10, 8))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(side="left")
        self.open_btn = ttk.Button(header, text="Open Folder", command=self.open_folder)
        self.open_btn.pack(side="right", padx=(6, 0))
        self.reset_btn = ttk.Button(header, text="Start Over", command=self.reset, state="disabled")
        self.reset_btn.pack(side="right", padx=(6, 6))

        # --- drop zone + canvas ---
        mid = ttk.Frame(root, padding=(10, 0))
        mid.pack(fill="both", expand=True)

        self.drop = tk.Label(
            mid,
            text=INSTRUCTIONS + ("\n(Drag-and-drop available)" if DND_AVAILABLE else "\n(Install 'tkinterdnd2' to enable drag-and-drop)"),
            relief="ridge", borderwidth=2, anchor="center", justify="center",
            fg="#333", font=("Segoe UI", 12),
        )
        self.drop.pack(fill="x", pady=(4, 8))
        self.drop.configure(height=4)
        if DND_AVAILABLE:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self.on_drop)

        canvas_wrap = ttk.Frame(mid)
        canvas_wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_wrap, width=CANVAS_W, height=CANVAS_H, bg="#111", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.render_image())

        # zoom & pan bindings
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._on_wheel_linux(1, e))   # Linux up
        self.canvas.bind("<Button-5>", lambda e: self._on_wheel_linux(-1, e))  # Linux down
        self.canvas.bind("<ButtonPress-1>", self._pan_start)
        self.canvas.bind("<B1-Motion>", self._pan_move)
        self.canvas.bind("<ButtonRelease-1>", self._pan_end)
        self.canvas.bind("<Double-Button-1>", lambda e: self.reset_view())

        # Zoom toolbar
        zbar = ttk.Frame(mid, padding=(10, 6))
        zbar.pack(fill="x")
        self.btn_zoom_out = ttk.Button(zbar, text="− Zoom Out",    command=lambda: self.zoom_step(0.9))
        self.btn_zoom_reset = ttk.Button(zbar, text="Reset (Fit)", command=self.reset_view)
        self.btn_zoom_in  = ttk.Button(zbar, text="+ Zoom In",     command=lambda: self.zoom_step(1.1))
        self.zoom_lbl = ttk.Label(zbar, text="100%", width=8, anchor="e")
        self.btn_zoom_out.pack(side="left", padx=(0,6))
        self.btn_zoom_reset.pack(side="left", padx=6)
        self.btn_zoom_in.pack(side="left", padx=6)
        self.zoom_lbl.pack(side="right")

        # --- footer: progress + counts ---
        foot = ttk.Frame(root, padding=(10, 8))
        foot.pack(fill="x")
        self.progress = ttk.Progressbar(foot, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", side="left", expand=True, padx=(0, 12))
        self.count_lbl = ttk.Label(foot, text="Labeled: 0 / 0  |  Solid:0  Sputter:0  Garbage:0  Flag:0", anchor="e")
        self.count_lbl.pack(side="left")

        # --- action buttons ---
        btns = ttk.Frame(root, padding=(10, 4))
        btns.pack(fill="x")
        self.btn_solid   = ttk.Button(btns, text="Solid [1]",   command=partial(self.apply_label, "Solid"),   state="disabled")
        self.btn_sputter = ttk.Button(btns, text="Sputter [2]", command=partial(self.apply_label, "Sputter"), state="disabled")
        self.btn_garbage = ttk.Button(btns, text="Garbage [3]", command=partial(self.apply_label, "Garbage"), state="disabled")
        self.btn_flag    = ttk.Button(btns, text="Flag [4/F]",  command=partial(self.apply_label, "Flag"),    state="disabled")
        self.btn_clear   = ttk.Button(btns, text="Clear [C]",   command=self.clear_label, state="disabled")
        self.btn_undo    = ttk.Button(btns, text="Undo [Z]",    command=self.undo_action, state="disabled")
        self.btn_prev    = ttk.Button(btns, text="◀ Prev [←]",  command=self.prev_image,  state="disabled")
        self.btn_next    = ttk.Button(btns, text="Next [→] ▶",  command=self.next_image,  state="disabled")
        for b in (self.btn_solid, self.btn_sputter, self.btn_garbage, self.btn_flag, self.btn_clear, self.btn_undo, self.btn_prev, self.btn_next):
            b.pack(side="left", padx=6)

        # --- help text ---
        helpf = ttk.Frame(root, padding=(10, 2))
        helpf.pack(fill="x")
        ttk.Label(helpf, text="Solid: keep • Sputter: imperfect • Garbage: discard • Flag: review • Clear: remove label (deletes copy; original stays in main folder). After labeling, it auto-advances.",
                  foreground="#555").pack(side="left")

        # --- keys ---
        self.root.bind("<KeyPress-1>", lambda e: self.apply_label("Solid"))
        self.root.bind("<KeyPress-2>", lambda e: self.apply_label("Sputter"))
        self.root.bind("<KeyPress-3>", lambda e: self.apply_label("Garbage"))
        self.root.bind("<KeyPress-4>", lambda e: self.apply_label("Flag"))
        self.root.bind("<KeyPress-f>", lambda e: self.apply_label("Flag"))
        self.root.bind("<KeyPress-F>", lambda e: self.apply_label("Flag"))
        self.root.bind("<KeyPress-c>", lambda e: self.clear_label())
        self.root.bind("<KeyPress-C>", lambda e: self.clear_label())
        self.root.bind("<KeyPress-z>", lambda e: self.undo_action())
        self.root.bind("<KeyPress-Z>", lambda e: self.undo_action())
        self.root.bind("<Left>",      lambda e: self.prev_image())
        self.root.bind("<Right>",     lambda e: self.next_image())
        # Zoom keys
        self.root.bind("<plus>",      lambda e: self.zoom_step(1.1))
        self.root.bind("<KP_Add>",    lambda e: self.zoom_step(1.1))
        self.root.bind("<minus>",     lambda e: self.zoom_step(0.9))
        self.root.bind("<KP_Subtract>", lambda e: self.zoom_step(0.9))
        self.root.bind("0",           lambda e: self.reset_view())

        self.status("Pick a folder to begin.")

    # ---------- folder handling ----------

    def on_drop(self, event):
        raw = event.data.strip()
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        p = Path(raw)
        if p.exists():
            self.load_folder(p if p.is_dir() else p.parent)
        else:
            messagebox.showerror(APP_TITLE, "Dropped path not found.")

    def open_folder(self):
        sel = filedialog.askdirectory(title="Choose a folder of images")
        if sel:
            self.load_folder(Path(sel))

    def load_folder(self, folder: Path):
        self.folder = folder
        for name in CATEGORIES:
            (folder / name).mkdir(exist_ok=True)

        # Pool = originals only (main folder), copies live in category subfolders
        originals = []
        for child in folder.iterdir():
            if child.is_dir() and child.name in CATEGORIES:
                continue
            if child.is_file() and child.suffix.lower() in IMAGE_EXTS:
                originals.append(child)
        originals.sort(key=natural_key)

        self.entries = []
        for orig in originals:
            label, copy_path = self._detect_existing_label(folder, orig.name)
            self.entries.append({
                "orig_name": orig.name,
                "root": folder,
                "orig_path": orig,
                "label": label,          # None or a category
                "copy_path": copy_path,  # Path to the copy inside category, or None
                "pil": None
            })

        self.index = 0
        self.history.clear()
        self.enable_controls(bool(self.entries))
        self.reset_btn.config(state="normal" if self.entries else "disabled")
        self.refresh_progress()
        self.drop.config(text=f"Folder: {folder}\nDrag another folder or click Open Folder to switch.")
        self.show_current()

    def _detect_existing_label(self, root: Path, filename: str):
        """Look through category subfolders for a copy of filename; return (label, path) or (None, None)."""
        for cat in CATEGORIES:
            p = root / cat / filename
            if p.exists():
                return cat, p
        return None, None

    def enable_controls(self, enable: bool):
        state = "normal" if enable else "disabled"
        for b in (self.btn_solid, self.btn_sputter, self.btn_garbage, self.btn_flag,
                  self.btn_clear, self.btn_undo, self.btn_prev, self.btn_next,
                  self.btn_zoom_in, self.btn_zoom_out, self.btn_zoom_reset):
            b.config(state=state)

    # ---------- labeling: COPY/MOVE/DELETE copies, never originals ----------

    def apply_label(self, new_label: str):
        if not self.entries:
            return
        entry = self.entries[self.index]
        prev_label = entry["label"]
        prev_copy  = entry["copy_path"]
        root = entry["root"]
        orig = entry["orig_path"]

        # If same label already set, just auto-advance
        if prev_label == new_label:
            self._auto_advance()
            return

        if prev_label is None:
            # Create a new copy in the target category
            target = self._unique_dest((root / new_label) / entry["orig_name"])
            try:
                shutil.copy2(str(orig), str(target))
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"Could not copy file:\n{e}")
                return
            entry["label"] = new_label
            entry["copy_path"] = target
            self.history.append({
                "action": "copy_create",
                "idx": self.index,
                "prev_label": prev_label,
                "prev_copy_path": prev_copy,
                "new_label": new_label,
                "new_copy_path": target,
            })
        else:
            # Move the existing copy from prev_label to new_label
            # Prefer keeping the same filename; ensure uniqueness at destination
            target = self._unique_dest((root / new_label) / entry["orig_name"])
            try:
                shutil.move(str(prev_copy), str(target))
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"Could not move labeled copy:\n{e}")
                return
            entry["label"] = new_label
            entry["copy_path"] = target
            self.history.append({
                "action": "copy_move",
                "idx": self.index,
                "prev_label": prev_label,
                "prev_copy_path": prev_copy,
                "new_label": new_label,
                "new_copy_path": target,
            })

        self.btn_undo.config(state="normal")
        self.refresh_progress()
        # Auto-advance after labeling
        self._auto_advance()

    def clear_label(self):
        if not self.entries:
            return
        entry = self.entries[self.index]
        if entry["label"] is None:
            return

        prev_label = entry["label"]
        prev_copy  = entry["copy_path"]

        # Delete the copy from its category folder; original stays
        try:
            if prev_copy and prev_copy.exists():
                prev_copy.unlink()
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not delete labeled copy:\n{e}")
            return

        entry["label"] = None
        entry["copy_path"] = None

        self.history.append({
            "action": "copy_delete",
            "idx": self.index,
            "prev_label": prev_label,
            "prev_copy_path": prev_copy,
            "new_label": None,
            "new_copy_path": None,
        })
        self.btn_undo.config(state="normal")
        self.refresh_progress()
        self.show_current()  # no auto-advance on clear by request

    def undo_action(self):
        if not self.history:
            return
        h = self.history.pop()
        idx = h["idx"]
        entry = self.entries[idx]

        act = h["action"]
        try:
            if act == "copy_create":
                # Remove the created copy
                p = h["new_copy_path"]
                if p and p.exists():
                    p.unlink()
                entry["label"] = h["prev_label"]
                entry["copy_path"] = h["prev_copy_path"]
            elif act == "copy_move":
                # Move copy back to previous location (ensure uniqueness)
                src = h["new_copy_path"]
                dst = h["prev_copy_path"]
                if src and src.exists():
                    if dst is None:
                        # should not happen for moves, but guard
                        dst = (entry["root"] / h["prev_label"] / entry["orig_name"])
                    dst = self._unique_dest(dst)
                    shutil.move(str(src), str(dst))
                entry["label"] = h["prev_label"]
                entry["copy_path"] = dst
            elif act == "copy_delete":
                # Recreate the deleted copy in its original category path (or unique path)
                dst = h["prev_copy_path"]
                if dst is None:
                    dst = (entry["root"] / h["prev_label"] / entry["orig_name"])
                # If name now taken, create a unique one
                dst = self._unique_dest(dst)
                shutil.copy2(str(entry["orig_path"]), str(dst))
                entry["label"] = h["prev_label"]
                entry["copy_path"] = dst
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Undo failed:\n{e}")
            # If undo fails, don't discard the history we just popped? We keep it popped to avoid loops.

        if not self.history:
            self.btn_undo.config(state="disabled")

        self.refresh_progress()
        if idx == self.index:
            self.show_current()

    # ---------- navigation ----------

    def _auto_advance(self):
        # advance to next; wrap around; refresh view
        if not self.entries:
            return
        self.index = (self.index + 1) % len(self.entries)
        self.show_current()

    def prev_image(self):
        if not self.entries:
            return
        self.index = (self.index - 1) % len(self.entries)
        self.show_current()

    def next_image(self):
        if not self.entries:
            return
        self.index = (self.index + 1) % len(self.entries)
        self.show_current()

    # ---------- zoom & pan ----------

    def reset_view(self):
        self.base_fit_scale = 1.0
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.render_image()

    def zoom_step(self, factor: float, cx=None, cy=None):
        if not self.entries:
            return
        if cx is None or cy is None:
            cw = self.canvas.winfo_width(); ch = self.canvas.winfo_height()
            cx, cy = cw/2, ch/2
        new_zoom = min(self.max_zoom, max(self.min_zoom, self.zoom * factor))
        self._zoom_at_canvas_point(cx, cy, new_zoom)

    def _on_wheel(self, event):
        if event.delta == 0:
            return
        factor = 1.1 if event.delta > 0 else 0.9
        self.zoom_step(factor, event.x, event.y)

    def _on_wheel_linux(self, direction, event):
        factor = 1.1 if direction > 0 else 0.9
        self.zoom_step(factor, event.x, event.y)

    def _pan_start(self, event):
        self.panning = True
        self.pan_start = (event.x, event.y)

    def _pan_move(self, event):
        if not self.panning:
            return
        dx = event.x - self.pan_start[0]
        dy = event.y - self.pan_start[1]
        self.pan_start = (event.x, event.y)
        self.pan_x += dx
        self.pan_y += dy
        self.render_image()

    def _pan_end(self, event):
        self.panning = False

    def _zoom_at_canvas_point(self, cx, cy, new_zoom):
        if not self.entries:
            return
        entry = self.entries[self.index]
        pil = self._get_pil(entry)
        iw, ih = pil.size
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()

        fit = self._compute_fit_scale(iw, ih, cw, ch)
        S  = fit * self.zoom
        iW = max(1, int(iw * S)); iH = max(1, int(ih * S))
        TLx = (cw - iW) / 2 + self.pan_x
        TLy = (ch - iH) / 2 + self.pan_y

        if S <= 0:
            return
        u = (cx - TLx) / S
        v = (cy - TLy) / S

        self.zoom = new_zoom
        S2  = fit * self.zoom
        iW2 = max(1, int(iw * S2)); iH2 = max(1, int(ih * S2))
        TLx2 = cx - u * S2
        TLy2 = cy - v * S2
        self.pan_x = TLx2 - (cw - iW2) / 2
        self.pan_y = TLy2 - (ch - iH2) / 2

        self.render_image()

    # ---------- UI refresh ----------

    def show_current(self):
        self.canvas_delete_all()
        if not self.entries:
            self.status("No images found in this folder.")
            self.progress.config(value=0, maximum=1)
            self.count_lbl.config(text="Labeled: 0 / 0  |  Solid:0  Sputter:0  Garbage:0  Flag:0")
            return

        # reset zoom/pan for each image
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0

        entry = self.entries[self.index]
        label = entry["label"]
        img_path: Path = entry["orig_path"]  # display original

        self.status(f"{img_path.name}  [{self.index+1}/{len(self.entries)}]  — Label: {label if label else 'Unlabeled'}")

        pil = self._get_pil(entry)
        if pil is None:
            self.status(f"Failed to open {img_path.name}")
            return

        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.base_fit_scale = self._compute_fit_scale(pil.size[0], pil.size[1], cw, ch)
        self.render_image()

    def render_image(self):
        self.canvas_delete_all()
        if not self.entries:
            return

        entry = self.entries[self.index]
        pil = self._get_pil(entry)
        if pil is None:
            return
        iw, ih = pil.size
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()

        S = self._compute_fit_scale(iw, ih, cw, ch) * self.zoom
        self.base_fit_scale = self._compute_fit_scale(iw, ih, cw, ch)
        disp_w, disp_h = max(1, int(iw * S)), max(1, int(ih * S))
        img = pil.resize((disp_w, disp_h), Image.LANCZOS)

        self.tk_img = ImageTk.PhotoImage(img)
        TLx = (cw - disp_w) // 2 + int(self.pan_x)
        TLy = (ch - disp_h) // 2 + int(self.pan_y)
        self.canvas.create_image(TLx, TLy, anchor="nw", image=self.tk_img)

        # filename strip
        self.canvas.create_rectangle(0, ch - 30, cw, ch, fill="#000", stipple="gray25", outline="")
        self.canvas.create_text(10, ch - 15, text=entry["orig_path"].name, anchor="w", fill="#fff", font=("Segoe UI", 10))

        # status badge
        label = entry["label"]
        badge_text = "Unlabeled" if label is None else label
        badge_color = {
            None: "#777",
            "Solid": "#2aa198",
            "Sputter": "#b58900",
            "Garbage": "#dc322f",
            "Flag": "#6c71c4",
        }.get(label, "#777")
        bx2, by2 = cw - 10, 10 + 28
        bx1, by1 = cw - 10 - 160, 10
        self.canvas.create_rectangle(bx1, by1, bx2, by2, fill="#000", stipple="gray25", outline="")
        self.canvas.create_text(bx1 + 8, by1 + 14, text=f"Status: {badge_text}", anchor="w", fill=badge_color, font=("Segoe UI", 11, "bold"))

        # index footer
        self.canvas.create_text(cw - 10, ch - 15, text=f"{self.index+1} / {len(self.entries)}",
                                anchor="e", fill="#fff", font=("Segoe UI", 10))

        # zoom label
        pct = int(round(self.zoom * 100))
        self.zoom_lbl.config(text=f"{pct}%")

    def refresh_progress(self):
        counts = {c: 0 for c in CATEGORIES}; labeled = 0
        for e in self.entries:
            if e["label"] in CATEGORIES:
                labeled += 1; counts[e["label"]] += 1
        total = len(self.entries)
        self.progress.config(maximum=max(1, total), value=labeled)
        self.count_lbl.config(
            text=f"Labeled: {labeled} / {total}  |  "
                 f"Solid:{counts['Solid']}  Sputter:{counts['Sputter']}  Garbage:{counts['Garbage']}  Flag:{counts['Flag']}"
        )

    # ---------- helpers ----------

    def _get_pil(self, entry):
        if entry["pil"] is None:
            try:
                entry["pil"] = Image.open(entry["orig_path"]).convert("RGB")
            except Exception:
                entry["pil"] = None
        return entry["pil"]

    @staticmethod
    def _compute_fit_scale(iw, ih, cw, ch):
        if iw <= 0 or ih <= 0: return 1.0
        return min(cw / iw, ch / ih)

    def canvas_delete_all(self):
        self.canvas.delete("all")
        self.canvas.config(width=self.canvas.winfo_width(), height=self.canvas.winfo_height())

    def status(self, text: str):
        self.root.title(f"{APP_TITLE} — {text}")

    def _unique_dest(self, candidate: Path) -> Path:
        """Return a unique path. If candidate exists, append (1), (2), ..."""
        if not candidate.exists():
            return candidate
        stem, suffix = candidate.stem, candidate.suffix
        i = 1
        while True:
            trial = candidate.with_name(f"{stem} ({i}){suffix}")
            if not trial.exists():
                return trial
            i += 1

    def reset(self):
        self.folder = None
        self.entries = []
        self.index = 0
        self.history.clear()
        self.enable_controls(False)
        self.reset_btn.config(state="disabled")
        self.progress.config(value=0, maximum=1)
        self.count_lbl.config(text="Labeled: 0 / 0  |  Solid:0  Sputter:0  Garbage:0  Flag:0")
        self.drop.config(text=INSTRUCTIONS + ("\n(Drag-and-drop available)" if DND_AVAILABLE else "\n(Install 'tkinterdnd2' to enable drag-and-drop)"))
        self.canvas_delete_all()
        self.status("Pick a folder to begin.")

def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    try:
        style = ttk.Style(root)
        if sys.platform.startswith("win"):
            style.theme_use("vista")
    except Exception:
        pass
    app = SolidOrSputterApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
