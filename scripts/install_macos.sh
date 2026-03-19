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

# Request microphone permission now (while running interactively).
# The launchd service has no UI to show the macOS permission prompt,
# so we must trigger it here. Uses the Python venv (instant via ctypes,
# no Swift compilation).
PYTHON="$SCRIPT_DIR/.venv/bin/python"
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
    echo "WARNING: Microphone access was previously denied."
    echo "  Go to System Settings → Privacy & Security → Microphone"
    echo "  and toggle access on for your terminal app."
    echo ""
fi

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
        <string>$TRANSCRIBE_BIN</string>
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
echo "IMPORTANT: Grant accessibility permissions"
echo "  System Settings → Privacy & Security → Accessibility"
echo "  Add your terminal app (Terminal.app, iTerm2, etc.)"
echo ""
echo "To start now:  launchctl start $PLIST_NAME"
echo "To stop:       launchctl stop $PLIST_NAME"
echo "Logs:          /tmp/transcribe.std{out,err}.log"
