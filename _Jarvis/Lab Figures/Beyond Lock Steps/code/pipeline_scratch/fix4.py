import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_figs.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (a[:60], s.count(a))
    s = s.replace(a, b)


rep('OUT = r"c:\\Users\\Z390\\Desktop\\DS_PTEN_figures_2026-11-16"\n',
    'UNC = "--uncorrected" in sys.argv\nOUT = r"c:\\Users\\Z390\\Desktop\\DS_PTEN_figures_2026-11-16" + ("\\\\uncorrected" if UNC else "")\n')
rep('def save(fig, stem):\n', 'def save(fig, stem):\n    if UNC:\n        stem += "_UNCORRECTED"\n        fig.text(0.995, 0.993, "UNCORRECTED", fontsize=8, fontweight="bold", color="#B5361F", ha="right", va="top")\n')
rep('''    axl.text(0.0, 0.66, "One recording per mouse.\\nControl n = 8, PTEN n = 9.\\n\\nAfter correction over these\\n%d tests the smallest q is %.2f:\\nno measure separates the groups." % (2 * n, qmin),''',
    '''    axl.text(0.0, 0.66, ("One recording per mouse.\\nControl n = 8, PTEN n = 9.\\n\\nRaw P values: no correction\\nfor the %d tests shown." % (2 * n)) if UNC else "One recording per mouse.\\nControl n = 8, PTEN n = 9.\\n\\nAfter correction over these\\n%d tests the smallest q is %.2f:\\nno measure separates the groups." % (2 * n, qmin),''')
rep('rp.correlation, rp.pvalue)).replace("-", "−")', 'rp.correlation, rp.pvalue)).replace("-", "−").replace("\\nuncorrected", "" if UNC else "\\nuncorrected")')
rep('    # d  what the whole search gives by chance\n',
    '    if UNC:\n        save(fig, "Fig3_PTEN_against_control")\n        return {"rho_all": (ra.correlation, ra.pvalue), "rho_pten": (rp.correlation, rp.pvalue)}\n    # d  what the whole search gives by chance\n')
rep('    which = sys.argv[1:] or ["1", "2", "3"]', '    which = [a for a in sys.argv[1:] if not a.startswith("--")] or ["1", "2", "3"]')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
