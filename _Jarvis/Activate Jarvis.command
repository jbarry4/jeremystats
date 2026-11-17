#!/bin/bash
# Jarvis -- macOS launcher. Double-click this file in Finder.
#
# If macOS says it cannot be opened, right-click it and choose Open. If it
# says you do not have permission, run once in Terminal:
#     chmod +x "Activate Jarvis.command"
# Jarvis puts that bit back by itself every time it starts, so it is a
# one-off (app/backend/launchers.py).

# Everything but the launchers lives in app/ beside this file.
cd "$(dirname "$0")/app" || exit 1

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
    echo "  Jarvis exited with an error. See the messages above."
    echo "  If packages are missing, run \"Setup Mac.command\"."
    read -r -p "  Press Enter to close..."
fi
