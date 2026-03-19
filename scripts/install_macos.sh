#!/usr/bin/env bash
# Install mpe-transcribe as a macOS launchd agent (auto-start on login).
set -euo pipefail

PLIST_NAME="com.mpe.transcribe"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$PLIST_NAME.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Resolve the transcribe binary
TRANSCRIBE_BIN="$(command -v transcribe 2>/dev/null || echo "$SCRIPT_DIR/.venv/bin/transcribe")"

if [ ! -x "$TRANSCRIBE_BIN" ]; then
    echo "Error: transcribe binary not found."
    echo "Install first:  uv pip install -e '.[macos]'"
    exit 1
fi

PYTHON="$SCRIPT_DIR/.venv/bin/python"

# Resolve the real Python binary (follow symlinks).
# macOS readlink doesn't support -f, so use Python itself.
PYTHON_REAL=$("$PYTHON" -c "import sys; print(sys.executable)" 2>/dev/null || echo "$PYTHON")

# Ad-hoc codesign the Python binary so that macOS TCC can track
# its permissions. Without a code signature, macOS cannot persist
# microphone/accessibility grants and the binary won't appear in
# System Settings.
# NOTE: Only sign the real Python binary — the "transcribe" entry
# point is a text wrapper script (shebang), not a binary.
echo "==> Codesigning Python binary for macOS permissions..."
codesign -s - -f "$PYTHON_REAL" 2>/dev/null || true
echo "    Signed: $PYTHON_REAL"

# Request microphone permission now (while running interactively).
# The launchd service has no UI to show the macOS permission prompt,
# so we must trigger it here.
echo "==> Checking microphone permissions..."
MIC_STATUS=$("$PYTHON" -c "from transcribe.macos_permissions import get_microphone_status; print(get_microphone_status())" 2>/dev/null || echo "unknown")

if [ "$MIC_STATUS" = "not_determined" ]; then
    echo "==> Requesting microphone access (grant in the system dialog)..."
    "$PYTHON" -c "
from transcribe.macos_permissions import request_microphone_access
granted = request_microphone_access()
print('granted' if granted else 'denied')
" 2>/dev/null
    echo ""
elif [ "$MIC_STATUS" = "authorized" ]; then
    echo "    Microphone access already granted."
elif [ "$MIC_STATUS" = "denied" ] || [ "$MIC_STATUS" = "restricted" ]; then
    echo ""
    echo "WARNING: Microphone access was previously denied."
    echo "  Reset with: tccutil reset Microphone"
    echo "  Then re-run this install script."
    echo ""
fi

# Trigger accessibility prompt — macOS will show a dialog guiding
# the user to System Settings → Accessibility.
echo "==> Checking accessibility permissions..."
"$PYTHON" -c "
from transcribe.macos_permissions import request_accessibility
request_accessibility()
" 2>/dev/null

mkdir -p "$PLIST_DIR"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_REAL</string>
        <string>-m</string>
        <string>transcribe</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/transcribe.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/transcribe.stderr.log</string>
</dict>
</plist>
PLIST

launchctl load "$PLIST_PATH" 2>/dev/null || true

echo "Installed launchd agent: $PLIST_PATH"
echo "The service will start automatically on login."
echo ""
echo "IMPORTANT: Grant permissions for the Python binary:"
echo "  $PYTHON_REAL"
echo ""
echo "  System Settings → Privacy & Security → Accessibility"
echo "    Add the Python binary above (drag it in, or use + to browse)"
echo ""
echo "  System Settings → Privacy & Security → Microphone"
echo "    The Python binary should appear after granting mic access above."
echo "    If not, run: uv run transcribe  (from the terminal, then Ctrl+C)"
echo ""
echo "To start now:  launchctl start $PLIST_NAME"
echo "To stop:       launchctl stop $PLIST_NAME"
echo "Logs:          /tmp/transcribe.std{out,err}.log"
