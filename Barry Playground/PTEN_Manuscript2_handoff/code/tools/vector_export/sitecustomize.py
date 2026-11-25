"""Vector export for every figure script in this package, without editing the scripts.

Usage (from the package folder):
    PYTHONPATH=tools/vector_export VEC_OUT=/path/to/folder python path_analysis/s03_example_mice_figs.py
Every figure a script saves as .png is also written to VEC_OUT as:
    <name>.pdf          vector, text kept as real (editable) text, fonts embedded as TrueType
    <name>.svg          vector, text kept as text
    <name>_600dpi.png   600 dpi raster
Set VEC_TEXT=path to write the SVGs with text converted to outlines instead (no font needed to view them;
this is what the report's Word/PDF build uses). Set INTER_TTF_DIR to a folder of Inter .ttf files to embed
the TrueType build of Inter; the OpenType (.otf) build embeds poorly in PDF.
"""
import os, glob
try:
    import matplotlib
    from matplotlib import font_manager as fm
    ttf = os.environ.get('INTER_TTF_DIR')
    if ttf and glob.glob(os.path.join(ttf, '*.ttf')):
        fm.fontManager.ttflist = [f for f in fm.fontManager.ttflist if not (f.fname.endswith('.otf') and 'Inter' in f.name)]
        for p in glob.glob(os.path.join(ttf, '*.ttf')): fm.fontManager.addfont(p)
    svgtext = 'path' if os.environ.get('VEC_TEXT') == 'path' else 'none'
    from matplotlib.figure import Figure
    _orig = Figure.savefig
    def savefig(self, fname, *a, **k):
        _orig(self, fname, *a, **k)
        out = os.environ.get('VEC_OUT')
        if out and isinstance(fname, str) and fname.lower().endswith('.png'):
            os.makedirs(out, exist_ok=True)
            name = os.path.basename(fname)[:-4]; k2 = {kk: v for kk, v in k.items() if kk != 'dpi'}
            matplotlib.rcParams['pdf.fonttype'] = 42; matplotlib.rcParams['svg.fonttype'] = svgtext
            _orig(self, os.path.join(out, name + '.pdf'), *a, **k2)
            _orig(self, os.path.join(out, name + '.svg'), *a, **k2)
            _orig(self, os.path.join(out, name + '_600dpi.png'), *a, **{**k2, 'dpi': 600})
    Figure.savefig = savefig
except Exception as e:
    print('vector export patch not applied:', e)
