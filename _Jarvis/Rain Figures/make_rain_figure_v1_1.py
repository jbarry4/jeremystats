"""Rain's figure, version 1.1: version 1 with cell layers, a tighter layout
and the H3 probe pitch (see make_rain_figure_x1.py).

    python make_rain_figure_v1_1.py      -> Rain_Figure_v1.1.pdf (+ preview PNG, panels)
"""
import make_rain_figure_x1 as X

X.CSD_CMAP = "RdBu_r"
X.OUT_STEM = "Rain_Figure_v1.1"

if __name__ == "__main__":
    X.main()
