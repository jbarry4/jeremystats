# -*- coding: utf-8 -*-
"""Heavy libraries, imported the first time they are used.

`app.py` imports every backend module when the server starts, so any
module-level `import scipy.signal` runs at start-up whether or not anybody
ever opens the tool that needs it. Measured on a lab machine: about 3 of the
3.6 s before the server could serve were imports of that kind -- scipy.signal
alone about a second, scikit-learn half a second. On a laptop, where antivirus
scans every compiled library the first time it loads, several times that.

And because a package is paid for by whichever module imports it FIRST,
fixing one module only moves the cost to the next: making `cfc` lazy handed
the whole second to `csc`, which imported the same thing. The cost goes only
when every module-level import of it is lazy, so they all go through here.

    from . import lazyimp

    _sig = lazyimp.module("scipy.signal")          # was: from scipy import signal as _sig
    butter, sosfiltfilt = lazyimp.names("scipy.signal", "butter", "sosfiltfilt")
    HAVE_SCIPY = lazyimp.have("scipy")             # was: try: import ... except

`have` asks the import system's index whether a package is installed, which
costs nothing and imports nothing -- so "X-ray needs scikit-learn, which is
not installed here" is still known at start-up, as it was when the import was
guarded, and a missing library still costs one tool rather than the server.

Constitution section 10: import what you use, when you use it.
"""
import importlib
import importlib.util


def have(package):
    """Whether `package` is installed, without importing it."""
    try:
        return importlib.util.find_spec(package) is not None
    except (ImportError, ValueError):
        return False


class _Module(object):
    """Stands in for a module until an attribute of it is first asked for."""

    def __init__(self, name):
        self.__dict__["_lazy_name"] = name
        self.__dict__["_lazy_mod"] = None

    def _lazy_load(self):
        mod = self.__dict__["_lazy_mod"]
        if mod is None:
            mod = importlib.import_module(self.__dict__["_lazy_name"])
            self.__dict__["_lazy_mod"] = mod
        return mod

    def __getattr__(self, attr):
        return getattr(self._lazy_load(), attr)

    def __setattr__(self, attr, value):
        setattr(self._lazy_load(), attr, value)

    def __repr__(self):
        return "<lazy %s>" % self.__dict__["_lazy_name"]


def module(name):
    """A module, imported on first attribute access."""
    return _Module(name)


def names(module_name, *attrs):
    """Callables from `module_name`, each importing it on its first call.

    For `from x import a, b` of FUNCTIONS and constructors. Not for classes
    used with isinstance, or for constants: those need the real object, so
    reach them through `module()` instead.
    """
    def one(attr):
        def call(*args, **kwargs):
            return getattr(importlib.import_module(module_name), attr)(
                *args, **kwargs)
        call.__name__ = attr
        call.__qualname__ = attr
        return call
    made = tuple(one(a) for a in attrs)
    return made[0] if len(made) == 1 else made
