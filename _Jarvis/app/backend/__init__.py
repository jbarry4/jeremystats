"""The Jarvis server.

Numerical thread pools, capped before anything imports numpy (2026-10-21).

numpy and scipy each bring their own OpenBLAS, and each reserves a buffer
per thread for as many threads as the machine has. Measured on the lab
desktop (12 threads): `import numpy` alone took the process from 8 MB to
388 MB of committed memory, `scipy.signal` to 820 MB -- before a single
request. Capped at four threads: 52 MB and 146 MB. On a laptop that memory
is the page file's, and twelve BLAS threads also fight the server's own
threads for a few cores. Four keeps large matrix work parallel.

`setdefault`, so anybody who has set these on purpose keeps theirs.
"""
import os as _os

_n = str(max(1, min(4, _os.cpu_count() or 4)))
for _k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    _os.environ.setdefault(_k, _n)
del _k, _n
