#!/usr/bin/env python3
import os
from pathlib import Path
from typing import List

from PIL import Image
from natsort import natsorted

from pptx import Presentation
from pptx.util import Pt
from pptx.enum.text import PP_ALIGN

from reportlab.lib.pagesizes import letter, A4, landscape, portrait
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}

def collect_images(folder: Path) -> List[Path]:
    imgs = [p for p in folder.iterdir() if p.suffix.lower() in SUPPORTED_EXTS]
    return natsorted(imgs, key=lambda p: p.name)

def best_pagesize(img_size, prefer="letter"):
    w, h = img_size
    base = A4 if prefer == "a4" else letter
    return landscape(base) if w >= h else portrait(base)

def add_slide(prs: Presentation, img_path: Path, margin_pts=36):
    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)

    slide_w = prs.slide_width
    slide_h = prs.slide_height

    def emu_to_pt(emu): return (emu / 914400.0) * 72.0
    def pt_to_emu(pt): return int((pt / 72.0) * 914400.0)

    slide_w_pt = emu_to_pt(slide_w)
    slide_h_pt = emu_to_pt(slide_h)

    with Image.open(img_path) as im:
        im = im.convert("RGB")
        img_w, img_h = im.size

        box_w = slide_w_pt - 2 * margin_pts
        box_h = slide_h_pt - 2 * margin_pts
        img_aspect = img_w / img_h
        box_aspect = box_w / box_h

        if img_aspect >= box_aspect:
            render_w = box_w
            render_h = box_w / img_aspect
        else:
            render_h = box_h
            render_w = box_h * img_aspect

        left = (slide_w_pt - render_w) / 2
        top = (slide_h_pt - render_h) / 2

        slide.shapes.add_picture(
            str(img_path),
            left=pt_to_emu(left),
            top=pt_to_emu(top),
            width=pt_to_emu(render_w),
            height=pt_to_emu(render_h)
        )

        # add filename label
        txbox = slide.shapes.add_textbox(pt_to_emu(8), pt_to_emu(8), pt_to_emu(slide_w_pt-16), pt_to_emu(20))
        tf = txbox.text_frame
        tf.clear()
        p = tf.paragraphs[0]
        p.text = img_path.name
        p.font.size = Pt(8)
        p.alignment = PP_ALIGN.LEFT

def build_pptx(images: List[Path], out_path: Path):
    prs = Presentation()
    for img in images:
        add_slide(prs, img)
    prs.save(str(out_path))

def build_pdf(images: List[Path], out_path: Path, margin=36, prefer="letter"):
    c = canvas.Canvas(str(out_path), pagesize=letter)
    for idx, p in enumerate(images, 1):
        with Image.open(p) as im:
            im = im.convert("RGB")
            page_size = best_pagesize(im.size, prefer)
            c.setPageSize(page_size)
            page_w, page_h = page_size

            img_w, img_h = im.size
            box_w = page_w - 2 * margin
            box_h = page_h - 2 * margin
            img_aspect = img_w / img_h
            box_aspect = box_w / box_h

            if img_aspect >= box_aspect:
                render_w = box_w
                render_h = box_w / img_aspect
            else:
                render_h = box_h
                render_w = box_h * img_aspect

            x = (page_w - render_w) / 2
            y = (page_h - render_h) / 2

            c.drawImage(ImageReader(im), x, y, width=render_w, height=render_h, preserveAspectRatio=True)

            c.setFont("Helvetica", 8)
            c.drawString(12, 12, f"{idx}/{len(images)} — {p.name}")
            c.showPage()
    c.save()

def main():
    script_dir = Path(__file__).resolve().parent
    images = collect_images(script_dir)
    if not images:
        print("No images found in script directory.")
        return

    pptx_path = script_dir / "images.pptx"
    pdf_path = script_dir / "images.pdf"

    print(f"Found {len(images)} images in {script_dir}")
    print(f"Writing PPTX: {pptx_path}")
    build_pptx(images, pptx_path)

    print(f"Writing PDF: {pdf_path}")
    build_pdf(images, pdf_path)

    print("Done.")

if __name__ == "__main__":
    main()
