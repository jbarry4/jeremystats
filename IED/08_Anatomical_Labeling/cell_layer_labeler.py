import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw

# --- Configuration ---
REGIONS = [
    "", "CA1 SP", "CA1", "CA1 SLM", "DG OML1", "DG MML1", 
    "DG GCL1", "HIL", "DG GCL2", "DG MML2", "DG OML2", "DG"
]

# Define semi-transparent colors for each region
# Format: Hex string
REGION_COLORS = {
    "CA1 SP": "#FF5733",   # Red-Orange
    "CA1": "#33FF57",      # Lime Green
    "CA1 SLM": "#3357FF",  # Blue
    "DG OML1": "#FF33F6",  # Magenta
    "DG MML1": "#33FFF6",  # Cyan
    "DG GCL1": "#F6FF33",  # Yellow
    "HIL": "#FF8C00",      # Dark Orange
    "DG GCL2": "#8A2BE2",  # BlueViolet
    "DG MML2": "#006400",  # DarkGreen
    "DG OML2": "#8B4513",  # SaddleBrown
    "DG": "#808080"        # Gray
}

ROW_COUNT = 64

def hex_to_rgba(hex_color, alpha=100):
    """Converts hex color to RGBA tuple with specified alpha (0-255)."""
    if not hex_color:
        return (0, 0, 0, 0)
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return rgb + (alpha,)

class ImagePanel(tk.Frame):
    """
    Manages the Image Canvas only.
    Controls are handled externally to ensure layout alignment.
    """
    def __init__(self, parent, bg_color="#555555"):
        super().__init__(parent, bg=bg_color)
        self.canvas = tk.Canvas(self, bg=bg_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.original_image = None
        self.photo_image = None
        self.overlay_photo = None
        
        # State variables set by parent
        self.row_height = 10
        self.offset = 0
        self.h_scale = 1.0
        self.w_scale = 1.0
        
        # Overlay state
        self.show_overlay = False
        self.labels = []

    def load_image(self, file_path):
        try:
            self.original_image = Image.open(file_path)
            # We do NOT reset parameters here. 
            # The existing offset/scale will apply to the new image immediately.
            self.redraw()
        except Exception as e:
            messagebox.showerror("Error", f"Could not load image: {e}")

    def clear_image(self):
        self.original_image = None
        self.canvas.delete("img")

    def update_params(self, row_height, offset, h_scale, w_scale, show_overlay=False, labels=None):
        self.row_height = row_height
        self.offset = offset
        self.h_scale = h_scale
        self.w_scale = w_scale
        self.show_overlay = show_overlay
        if labels is not None:
            self.labels = labels
        self.redraw()

    def redraw(self):
        # 1. Clear Canvas
        self.canvas.delete("all")
        
        # 2. Draw Image if exists
        if self.original_image:
            orig_w, orig_h = self.original_image.size
            target_w = int(orig_w * self.w_scale)
            target_h = int(orig_h * self.h_scale)
            
            # Optimization: Don't resize if dimensions are invalid
            if target_w > 0 and target_h > 0:
                resized = self.original_image.resize((target_w, target_h), Image.Resampling.LANCZOS)
                self.photo_image = ImageTk.PhotoImage(resized)
                self.canvas.create_image(0, self.offset, image=self.photo_image, anchor="nw", tags="img")

        # 3. Draw Color Overlay if enabled
        width = self.winfo_width()
        height = self.winfo_height()
        # Fallback if window not drawn yet
        if width < 50: width = 800
        if height < 50: height = 2000

        if self.show_overlay and self.labels:
            # Create a transparent image for the overlay
            overlay_img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay_img)
            
            for i, label in enumerate(self.labels):
                if label in REGION_COLORS:
                    color = hex_to_rgba(REGION_COLORS[label], alpha=80) # Semi-transparent
                    y_start = int(i * self.row_height)
                    y_end = int((i + 1) * self.row_height)
                    draw.rectangle([0, y_start, width, y_end], fill=color)
            
            self.overlay_photo = ImageTk.PhotoImage(overlay_img)
            self.canvas.create_image(0, 0, image=self.overlay_photo, anchor="nw", tags="overlay")

        # 4. Draw Grid Lines (Always draw these to show alignment)
        for i in range(ROW_COUNT):
            y = i * self.row_height
            # Top of row line (dotted)
            self.canvas.create_line(0, y, width, y, fill="#777777", dash=(1, 3), tags="grid")
            # Bottom of row line (red dashed - separation)
            y_bottom = (i + 1) * self.row_height
            self.canvas.create_line(0, y_bottom, width, y_bottom, fill="red", dash=(2, 4), tags="grid")


class ControlPanel(tk.Frame):
    """
    Holds the sliders and buttons for an image side.
    """
    def __init__(self, parent, title, on_update):
        super().__init__(parent, bg="#d0d0d0", padx=5, pady=5, relief="raised", bd=1)
        self.on_update = on_update
        
        # Title
        tk.Label(self, text=title, bg="#d0d0d0", font=("Arial", 10, "bold")).pack(fill="x", pady=2)
        
        # Buttons
        btn_frame = tk.Frame(self, bg="#d0d0d0")
        btn_frame.pack(fill="x", pady=2)
        tk.Button(btn_frame, text="Load", command=self.browse_image, width=8).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Clear", command=self.request_clear, width=8).pack(side="left", padx=2)

        # Sliders
        # Initializing these variables once ensures persistence across image loads
        self.offset_var = tk.DoubleVar(value=0)
        self.h_scale_var = tk.DoubleVar(value=1.0)
        self.w_scale_var = tk.DoubleVar(value=1.0)

        self._add_slider("V-Offset", self.offset_var, -200, 500)
        self._add_slider("H-Scale", self.h_scale_var, 0.1, 5.0)
        self._add_slider("W-Scale", self.w_scale_var, 0.1, 5.0)

    def _add_slider(self, label, variable, min_val, max_val):
        frame = tk.Frame(self, bg="#d0d0d0")
        frame.pack(fill="x")
        tk.Label(frame, text=label, width=8, anchor="w", bg="#d0d0d0", font=("Arial", 8)).pack(side="left")
        s = tk.Scale(frame, variable=variable, from_=min_val, to=max_val, orient="horizontal", 
                     resolution=0.01 if "Scale" in label else 1, showvalue=0, command=lambda x: self.on_update())
        s.pack(side="left", fill="x", expand=True)
        # Value label
        lbl = tk.Label(frame, text="0", width=4, bg="#d0d0d0", font=("Arial", 7))
        lbl.pack(side="right")
        # Update label on change
        def update_lbl(*args):
            val = variable.get()
            lbl.config(text=f"{val:.2f}" if "Scale" in label else f"{int(val)}")
        variable.trace("w", update_lbl)
        update_lbl()

    def browse_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.tif")])
        if path:
            self.on_update(path)

    def request_clear(self):
        self.on_update(clear=True)

class HippoLabeler(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hippo Labeler")
        self.geometry("1400x900")
        
        # --- Layout Architecture ---
        # Row 0: Toolbar
        # Row 1: Controls (Left, Center Header, Right)
        # Row 2: Content (Left Canvas, Center Inputs, Right Canvas)
        
        self.columnconfigure(0, weight=1) # Left Image Area
        self.columnconfigure(1, weight=0, minsize=220) # Center Input Area (Fixed width)
        self.columnconfigure(2, weight=1) # Right Image Area
        
        self.rowconfigure(2, weight=1) # Content row expands
        
        # Global Toggle State
        self.overlay_var = tk.BooleanVar(value=False)

        # --- Toolbar ---
        toolbar = tk.Frame(self, bg="#f0f0f0", bd=1, relief="raised")
        toolbar.grid(row=0, column=0, columnspan=3, sticky="ew")
        tk.Label(toolbar, text="Hippo Labeler", font=("Helvetica", 14, "bold"), bg="#f0f0f0").pack(side="left", padx=10)
        
        tk.Button(toolbar, text="Export CSV", command=self.export_csv, bg="#d4edda").pack(side="right", padx=10, pady=5)
        
        # Clear Labels Button (Added)
        tk.Button(toolbar, text="Clear Labels", command=self.clear_labels, bg="#f8d7da", fg="#721c24").pack(side="right", padx=10, pady=5)
        
        tk.Button(toolbar, text="Auto-Fill Down", command=self.autofill, bg="#e2e6ea").pack(side="right", padx=10, pady=5)
        
        # Overlay Checkbox
        tk.Checkbutton(toolbar, text="Show Color Overlay", variable=self.overlay_var, 
                       command=self.trigger_update, bg="#f0f0f0").pack(side="right", padx=20)

        # --- Controls (Row 1) ---
        self.ctrl_left = ControlPanel(self, "Left Image (Theta)", lambda p=None, c=False: self.update_left(p, c))
        self.ctrl_left.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        
        self.header_center = tk.Frame(self, bg="#d0d0d0", height=100, relief="raised", bd=1)
        self.header_center.grid(row=1, column=1, sticky="nsew", padx=2, pady=2)
        tk.Label(self.header_center, text="Regions", bg="#d0d0d0", font=("Arial", 12, "bold")).place(relx=0.5, rely=0.5, anchor="center")

        self.ctrl_right = ControlPanel(self, "Right Image (CSD)", lambda p=None, c=False: self.update_right(p, c))
        self.ctrl_right.grid(row=1, column=2, sticky="ew", padx=2, pady=2)

        # --- Content (Row 2) ---
        self.canvas_left = ImagePanel(self)
        self.canvas_left.grid(row=2, column=0, sticky="nsew", padx=2)
        
        # Center Frame for Inputs
        self.center_container = tk.Frame(self, bg="white", relief="sunken", bd=1)
        self.center_container.grid(row=2, column=1, sticky="nsew", padx=0)
        
        self.canvas_right = ImagePanel(self)
        self.canvas_right.grid(row=2, column=2, sticky="nsew", padx=2)

        # --- Initialize Inputs ---
        self.row_vars = []
        self.combos = []
        self.row_labels = []
        
        for i in range(ROW_COUNT):
            # Var
            var = tk.StringVar()
            self.row_vars.append(var)
            
            # Label (Number)
            lbl = tk.Label(self.center_container, text=f"{i+1}", font=("Arial", 8), fg="#888", bg="white")
            self.row_labels.append(lbl)
            
            # Combobox
            cb = ttk.Combobox(self.center_container, textvariable=var, values=REGIONS, state="readonly")
            cb.bind("<<ComboboxSelected>>", lambda e: self.trigger_update()) # Update overlay on change
            self.combos.append(cb)

        # --- Event Binding ---
        self.center_container.bind("<Configure>", self.on_resize)
        self.canvas_left.bind("<Configure>", lambda e: self.update_left())
        self.canvas_right.bind("<Configure>", lambda e: self.update_right())

    def trigger_update(self):
        """Helper to force update of both panels when toggles/combos change"""
        self.update_left(redraw_only=True)
        self.update_right(redraw_only=True)

    def on_resize(self, event):
        """
        Recalculate row height based on available window height 
        and reposition all 64 widgets.
        """
        available_height = event.height
        if available_height < 100: return # Startup safety
        
        # Dynamic Row Height
        row_h = available_height / ROW_COUNT
        
        # Update Input Positions
        for i in range(ROW_COUNT):
            y_pos = i * row_h
            
            # Number Label
            self.row_labels[i].place(x=2, y=y_pos, height=row_h, width=25)
            
            # Combobox
            box_h = max(row_h - 2, 1) 
            self.combos[i].place(x=30, y=y_pos + 1, height=box_h, relwidth=0.85)

        # Update Canvases
        self.update_left(redraw_only=True, new_row_h=row_h)
        self.update_right(redraw_only=True, new_row_h=row_h)

    def get_current_labels(self):
        return [var.get() for var in self.row_vars]

    def update_left(self, path=None, clear=False, redraw_only=False, new_row_h=None):
        if path: self.canvas_left.load_image(path)
        if clear: self.canvas_left.clear_image()
        
        # Get parameters
        row_h = new_row_h if new_row_h else (self.center_container.winfo_height() / ROW_COUNT)
        if row_h <= 0: row_h = 10
        
        self.canvas_left.update_params(
            row_height=row_h,
            offset=self.ctrl_left.offset_var.get(),
            h_scale=self.ctrl_left.h_scale_var.get(),
            w_scale=self.ctrl_left.w_scale_var.get(),
            show_overlay=self.overlay_var.get(),
            labels=self.get_current_labels()
        )

    def update_right(self, path=None, clear=False, redraw_only=False, new_row_h=None):
        if path: self.canvas_right.load_image(path)
        if clear: self.canvas_right.clear_image()
        
        row_h = new_row_h if new_row_h else (self.center_container.winfo_height() / ROW_COUNT)
        if row_h <= 0: row_h = 10

        self.canvas_right.update_params(
            row_height=row_h,
            offset=self.ctrl_right.offset_var.get(),
            h_scale=self.ctrl_right.h_scale_var.get(),
            w_scale=self.ctrl_right.w_scale_var.get(),
            show_overlay=self.overlay_var.get(),
            labels=self.get_current_labels()
        )

    def autofill(self):
        last_val = ""
        for var in self.row_vars:
            current = var.get()
            if current:
                last_val = current
            elif last_val:
                var.set(last_val)
        self.trigger_update() # Update overlays after autofill

    def clear_labels(self):
        if messagebox.askyesno("Confirm", "Are you sure you want to clear all labels?"):
            for var in self.row_vars:
                var.set("")
            self.trigger_update()

    def export_csv(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not file_path:
            return
        try:
            with open(file_path, "w") as f:
                f.write("Row,Region\n")
                for i, var in enumerate(self.row_vars):
                    val = var.get() if var.get() else "Unlabeled"
                    f.write(f"{i+1},{val}\n")
            messagebox.showinfo("Success", f"Saved to {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save file: {e}")

if __name__ == "__main__":
    app = HippoLabeler()
    app.mainloop()