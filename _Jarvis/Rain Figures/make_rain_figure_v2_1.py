"""Rain's figure, version 2.1: version 1.1 with the jet ("green at zero")
color map on the CSDs and spectrograms, as in version 2.

    python make_rain_figure_v2_1.py      -> Rain_Figure_v2.1.pdf (+ preview PNG, panels)
"""
import make_rain_figure_x1 as X

X.CSD_CMAP = "jet"
X.SPEC_CMAP = "jet"
X.OUT_STEM = "Rain_Figure_v2.1"

if __name__ == "__main__":
    X.main()
