"""Rain's figure, version 2: version 1's layout, data and voltage rasters
exactly, with the lab's jet ("green at zero") color map on the CSDs and
spectrograms, and even channel numbers on the CSD depth axes.

    python make_rain_figure_v2.py      -> Rain_Figure_v2.pdf (+ preview PNG)
"""
import make_rain_figure as M

M.CSD_CMAP = "jet"
M.SPEC_CMAP = "jet"
M.CHAN_TICKS = True
M.OUT_STEM = "Rain_Figure_v2"

if __name__ == "__main__":
    M.main()
