"""Stack existing figures into one multipanel sheet without redrawing them.

Each component keeps its own size, so the text in a stacked figure is exactly as large, relative
to the page, as it was in the single figure it came from.  That is the reason for stacking rather
than placing components side by side: side by side halves every component and the labels go with
it.

    python tools/compose_stack.py out.svg A=first.svg B=second.svg [...]

The letter before each '=' is drawn at the top left of that component.  Use '-' for no letter.
Components are centred on the widest one.  Sizes are read from each file's width/height in points.
"""
import sys, os, re

HEAD = ('<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'version="1.1" width="%(w).2fpt" height="%(h).2fpt" viewBox="0 0 %(w).2f %(h).2f">\n'
        '<rect width="%(w).2f" height="%(h).2f" fill="#fcfcfb"/>\n')
LETTER = ('<text x="%.2f" y="%.2f" font-family="Inter, Helvetica, Arial, sans-serif" '
          'font-size="13" font-weight="bold" fill="#0b0b0b">%s</text>\n')


def size(path):
    h = open(path, encoding='utf-8').read(800)
    w = float(re.search(r'width="([\d.]+)pt"', h).group(1))
    ht = float(re.search(r'height="([\d.]+)pt"', h).group(1))
    return w, ht


def body(path):
    """The file's content, without its own <svg> wrapper.

    A nested <svg> would be cleaner, but Word (through LibreOffice) clips nested svg elements, so
    the content is placed in a <g translate(...)> instead.  matplotlib writes viewBox equal to
    width/height in points, so no scaling is needed and a plain translate is exact.
    """
    s = open(path, encoding='utf-8').read()
    i = s.index('<svg'); j = s.index('>', i) + 1
    k = s.rindex('</svg>')
    return s[j:k]


def compose(out, items, gap=6.0, pad=2.0):
    sizes = [size(p) for _, p in items]
    W = max(w for w, _ in sizes) + 2 * pad
    H = sum(h for _, h in sizes) + gap * (len(items) - 1) + 2 * pad
    parts = [HEAD % {'w': W, 'h': H}]
    y = pad
    for (lab, p), (w, h) in zip(items, sizes):
        x = (W - w) / 2
        parts.append('<g transform="translate(%.2f,%.2f)">\n' % (x, y))
        parts.append(body(p))
        parts.append('</g>\n')
        if lab != '-':
            parts.append(LETTER % (x + 2, y + 13, lab))
        y += h + gap
    parts.append('</svg>\n')
    open(out, 'w', encoding='utf-8').write(''.join(parts))
    print('wrote %s  %.2f x %.2f in' % (out, W / 72, H / 72))


if __name__ == '__main__':
    out = sys.argv[1]
    items = []
    for a in sys.argv[2:]:
        lab, p = a.split('=', 1)
        items.append((lab, p))
    compose(out, items)
