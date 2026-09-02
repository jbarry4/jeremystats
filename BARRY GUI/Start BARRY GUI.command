#!/bin/bash
# BARRY GUI -- macOS launcher. Double-click this file in Finder.
#
# If macOS refuses to run it, right-click and choose Open, or run once:
#     chmod +x "Start BARRY GUI.command"

cd "$(dirname "$0")" || exit 1

PYEXE=""
for cand in python3.12 python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        PYEXE="$(command -v "$cand")"
        break
    fi
done

if [ -z "$PYEXE" ]; then
    echo "  Python 3 was not found. Run \"Setup Mac.command\" first."
    read -r -p "  Press Enter to close..."
    exit 1
fi

"$PYEXE" start.py
STATUS=$?

if [ $STATUS -ne 0 ]; then
    echo
    echo "  BARRY GUI exited with an error. See the messages above."
    echo "  If packages are missing, run \"Setup Mac.command\"."
    read -r -p "  Press Enter to close..."
fi
