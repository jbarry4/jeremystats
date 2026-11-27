import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_figs.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, a
    s = s.replace(a, b)


rep('ax.set_xlabel("Events, sorted by classifier score", fontsize=FS)', 'ax.set_xlabel("Events, sorted by score", fontsize=FS)')
rep('(0, 0.2, "not sep.", "#F3F3F3"), (0.2, 0.5, "partial", "#E9E9E9"), (0.5, 1.0, "separable", "#DEDEDE")',
    '(0, 0.2, "not sep.", "#F3F3F3"), (0.2, 0.45, "partial", "#E9E9E9"), (0.45, 1.0, "separable", "#DEDEDE")')
rep('["Separable\\n(n = %d)" % len(grp[0]), "Not\\nseparable\\n(n = %d)" % len(grp[1])], fontsize=FS_S)',
    '["Yes\\n(n = %d)" % len(grp[0]), "No\\n(n = %d)" % len(grp[1])], fontsize=FS_S)\n    ax.set_xlabel("DS1 and DS2\\nseparable", fontsize=FS)')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
