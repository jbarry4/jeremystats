import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # just save a PNG, don't try to pop up a window
import matplotlib.pyplot as plt

# ---- 1. Load data ----
SHEET = "2024 + 2026 data"
df = pd.read_excel("KCNT1_AA_2024_thru_June26_outputs.xlsx", sheet_name=SHEET)

# ---- 2. Metrics to plot against age (add/remove rows here) ----
# key: column name in the spreadsheet, value: readable axis label
METRICS = {
    "# of  shocks ": "Mean # of shocks per session",
    "# of entr.": "Mean # of entries per session",
    "time to first entr. [s]": "Mean time to first entry [s]",
    "time to_first shock [s]": "Mean time to first shock [s]",
    "linearity [0-1]": "Mean linearity [0-1]",
    "max. time avoid. [s]  ": "Mean max. time avoiding [s]",
}

# one row per mouse: age + genotype are fixed per mouse, everything else
# is averaged across that mouse's sessions
agg = {col: "mean" for col in METRICS}
agg["Age (weeks)"] = "first"
agg["YH"] = "first"
per_mouse = df.groupby("Mouse_ID", as_index=False).agg(agg)

# ---- 3. Colors (one per group, fixed order, colorblind-checked) ----
GROUP_COLORS = {
    "WT": "#2a78d6",   # blue
    "Het": "#eb6834",  # orange
    "Hom": "#1baf7a",  # aqua
}

# ---- 4. Grid of scatterplots, one per metric, with a trend line per group ----
n = len(METRICS)
cols = 3
rows = -(-n // cols)  # round up

fig, axes = plt.subplots(rows, cols, figsize=(5.5 * cols, 4.5 * rows))
axes = axes.flatten()

for ax, (col, label) in zip(axes, METRICS.items()):
    for group, color in GROUP_COLORS.items():
        sub = per_mouse[per_mouse["YH"] == group]
        x, y = sub["Age (weeks)"], sub[col]
        ax.scatter(x, y, label=group, color=color, s=50, edgecolor="white", linewidth=0.5)

        # straight-line trend (linear fit) for this group, needs >= 2 points
        if len(x) >= 2:
            slope, intercept = np.polyfit(x, y, 1)
            x_line = np.array([x.min(), x.max()])
            ax.plot(x_line, slope * x_line + intercept, color=color, linewidth=2)

    ax.set_xlabel("Age (weeks)")
    ax.set_ylabel(label)
    ax.grid(True, color="#e1e0d9", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)

# hide any unused empty subplots
for j in range(n, len(axes)):
    axes[j].axis("off")

# one shared legend for the whole figure instead of one per panel
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, title="Group", loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.02))

fig.suptitle("Active Avoidance Metrics vs. Age by Genotype", y=1.06, fontsize=14)
plt.tight_layout()
plt.savefig("scatter_metrics_vs_age.png", dpi=150, bbox_inches="tight")
