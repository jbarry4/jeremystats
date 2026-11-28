"""Run one of the pipeline scripts with Jarvis's recording lookup pointed at the cluster's copies (vaccpatch).

  ./py krun.py <script.py> [args...]
"""
import os
import runpy
import sys

script = os.path.abspath(sys.argv[1])        # before vaccpatch changes the working folder to the app
import vaccpatch  # noqa: E402,F401  (patches backend.app before the script imports it)

sys.argv = [script] + sys.argv[2:]
sys.path.insert(0, os.path.dirname(script))
runpy.run_path(script, run_name="__main__")
