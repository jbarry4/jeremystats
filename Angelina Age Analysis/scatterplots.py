import pandas as pd
import matplotlib.pyplot as plt

# 1. Load spreadsheet
df = pd.read_excel("data.xlsx")  # change to your file name (use pd.read_csv for .csv)

# 2. X axis column
x_col = "Age"

# 3. Y axis columns (add/remove as many as you want)
y_cols = ["Score1", "Score2", "Score3"]

# 4. Grid of scatterplots, one per y column
n = len(y_cols)
cols = 3  # how many charts per row
rows = -(-n // cols)  # round up

fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4 * rows))
axes = axes.flatten()  # makes indexing simple even if grid isn't 1D

for i, y_col in enumerate(y_cols):
    ax = axes[i]
    ax.scatter(df[x_col], df[y_col])
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title(y_col)

# hide any unused empty subplots
for j in range(n, len(axes)):
    axes[j].axis("off")

plt.tight_layout()
plt.show()
