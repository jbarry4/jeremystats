"""PTEN poster v5: the two photographs of the opening figure (panel A, a cued and a hidden probe session; panel G, Pten KO
dentate histology), taken as their embedded pictures only (the source's Helvetica titles and labels left behind) and
labelled in Aptos.

  X_task       the two arena photos: "Visible goal (cued)" / "Hidden goal", the goal marks V1 and H1 as on the source
  X_histology  the histology picture, with the blades named"""
import os
import numpy as np
import fitz
import style as S
from digitize_theta import OPEN, PXPT, picture_canvas

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
PG = fitz.open(OPEN)[0]


def crop(clip):
    can, got = picture_canvas(PG, fitz.Rect(clip))
    ys, xs = np.where(got)
    return can[ys.min():ys.max() + 1, xs.min():xs.max() + 1], (clip[0] + xs.min() / PXPT, clip[1] + ys.min() / PXPT)


def x_task():
    W, H = 4.4, 2.45
    fig = S.figure(W, H)
    for k, (clip, title, mark, mxy) in enumerate((((0, 24, 114.5, 128), "Visible goal (cued)", "V1", (77.6, 47.1)),
                                                  ((114.5, 24, 230, 128), "Hidden goal", "H1", (191.4, 47.1)))):
        im, (x0, y0) = crop(clip)
        w = 2.12
        h = w * im.shape[0] / im.shape[1]
        ax = S.ax_at(fig, 0.05 + k * (w + 0.12), 0.32, w, h)
        ax.imshow(im, extent=(x0, x0 + im.shape[1] / PXPT, y0 + im.shape[0] / PXPT, y0))
        ax.axis("off")
        ax.text(mxy[0], mxy[1], mark, ha="center", va="center", fontsize=S.SMALL, color="white", fontweight="bold")
        S.text_at(fig, 0.05 + k * (w + 0.12) + w / 2, 0.02, title, ha="center", fontsize=S.NOTE, fontweight="bold",
                  color=S.GREEN)
    S.save(fig, os.path.join(OUT, "X_task.png"))
    print("X_task")


def x_histology():
    im, (x0, y0) = crop((420, 305, 600, 440))
    w = 3.3
    h = w * im.shape[0] / im.shape[1]
    fig = S.figure(w, h)
    ax = S.ax_at(fig, 0, 0, w, h)
    ax.imshow(im)
    ax.axis("off")
    S.save(fig, os.path.join(OUT, "X_histology.png"))
    print("X_histology %.2f x %.2f in" % (w, h))


if __name__ == "__main__":
    x_task()
    x_histology()
