"""
Debug utility: dumps raw text + word geometry from a VOS PDF so we can see
exactly how the export format changed.

Usage:  python dump_pdf.py "..\\..\\VOS Report 072826.pdf"
"""
import sys
import os
import pdfplumber

pdf_path = sys.argv[1]
out_dir = os.path.dirname(os.path.abspath(__file__))
base = os.path.splitext(os.path.basename(pdf_path))[0]

text_out = os.path.join(out_dir, f'{base}__text_dump.txt')
words_out = os.path.join(out_dir, f'{base}__word_geometry.txt')

with pdfplumber.open(pdf_path) as pdf, \
     open(text_out, 'w', encoding='utf-8') as tf, \
     open(words_out, 'w', encoding='utf-8') as wf:

    tf.write(f'FILE: {pdf_path}\nPAGES: {len(pdf.pages)}\n')
    wf.write(f'FILE: {pdf_path}\nPAGES: {len(pdf.pages)}\n')

    for i, page in enumerate(pdf.pages, start=1):
        tf.write('\n' + '=' * 100 + f'\nPAGE {i}  (w={page.width:.1f} h={page.height:.1f})\n' + '=' * 100 + '\n')
        text = page.extract_text() or ''
        for ln, line in enumerate(text.split('\n'), start=1):
            tf.write(f'{ln:3d} | {line}\n')

        # Word geometry: helps detect column/card boundaries by x/y position
        wf.write('\n' + '=' * 100 + f'\nPAGE {i}  (w={page.width:.1f} h={page.height:.1f})\n' + '=' * 100 + '\n')
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        for w in words:
            wf.write(f"x0={w['x0']:7.2f} x1={w['x1']:7.2f} top={w['top']:7.2f} bottom={w['bottom']:7.2f}  {w['text']}\n")

        # Rectangles / lines: card borders would show up here
        wf.write(f"\n-- RECTS ({len(page.rects)}) --\n")
        for r in page.rects:
            wf.write(f"x0={r['x0']:7.2f} x1={r['x1']:7.2f} top={r['top']:7.2f} bottom={r['bottom']:7.2f}\n")
        wf.write(f"\n-- LINES ({len(page.lines)}) --\n")
        for l in page.lines:
            wf.write(f"x0={l['x0']:7.2f} x1={l['x1']:7.2f} top={l['top']:7.2f} bottom={l['bottom']:7.2f}\n")

print(f'Wrote {text_out}')
print(f'Wrote {words_out}')
