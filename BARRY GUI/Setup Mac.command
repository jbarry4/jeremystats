#!/bin/bash
# BARRY GUI -- macOS setup. Double-click this file in Finder.
#
# If macOS refuses to run it ("cannot be opened because it is from an
# unidentified developer"), right-click it and choose Open, or run once:
#     chmod +x "Setup Mac.command"

cd "$(dirname "$0")" || exit 1

echo
echo "  BARRY GUI setup"
echo "  ---------------"
echo

# Find a usable Python 3. macOS ships an old one, so prefer Homebrew's.
PYEXE=""
for cand in python3.12 python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        PYEXE="$(command -v "$cand")"
        break
    fi
done

if [ -z "$PYEXE" ]; then
    cat <<'EOF'
  Python 3 was not found on this Mac.

  Install it, then run this setup again:

    Option A - Homebrew (recommended):
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        brew install python

    Option B - download:
        https://www.python.org/downloads/macos/

EOF
    read -r -p "  Press Enter to close..."
    exit 1
fi

echo "  Using $PYEXE"
"$PYEXE" setup.py
STATUS=$?

if [ $STATUS -ne 0 ]; then
    echo
    echo "  Setup did not finish cleanly. See the messages above."
    read -r -p "  Press Enter to close..."
fi
