#!/bin/bash
# Jarvis -- macOS setup. Double-click this file in Finder.
#
# If macOS refuses to run it ("cannot be opened because it is from an
# unidentified developer"), right-click it and choose Open. If it says you do
# not have permission, run once in Terminal:
#     chmod +x "Setup Mac.command"

# Everything but the launchers lives in app/ beside this file.
cd "$(dirname "$0")/app" || exit 1

echo
echo "  Jarvis setup"
echo "  ------------"
echo

# Find a usable Python 3. macOS ships an old one, so prefer Homebrew's.
# One that RUNS: on a new Mac /usr/bin/python3 is a stand-in that only offers
# to install Apple's command line tools.
findpy() {
    PYEXE=""
    for cand in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$cand" >/dev/null 2>&1 \
           && "$cand" -c 'import sys' >/dev/null 2>&1; then
            PYEXE="$(command -v "$cand")"
            return
        fi
    done
}
findpy

if [ -z "$PYEXE" ] && [ -x /usr/bin/xcode-select ] \
   && ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
    # Apple's tools bring a Python 3. Installed here and waited for, so
    # nobody has to run Setup a second time once they are in.
    echo "  Python is not on this Mac yet. Apple's command line tools include"
    echo "  it: a window is opening to install them. Press Install there; this"
    echo "  setup carries on by itself once they are in (a few minutes)."
    /usr/bin/xcode-select --install >/dev/null 2>&1
    for _ in $(seq 1 180); do
        sleep 5
        findpy
        [ -n "$PYEXE" ] && break
    done
    echo
fi

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
