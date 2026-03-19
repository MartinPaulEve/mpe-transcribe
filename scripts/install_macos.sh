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
# so we must trigger it here. This will show the system dialog if
# permission has not yet been determined.
echo "==> Checking microphone permissions..."
MIC_STATUS=$(swift -e 'import AVFoundation; print(AVCaptureDevice.authorizationStatus(for: .audio).rawValue)' 2>/dev/null || echo "?")
if [ "$MIC_STATUS" = "0" ]; then
    echo "==> Requesting microphone access (grant in the system dialog)..."
    swift -e '
import AVFoundation
import Darwin
let sem = DispatchSemaphore(value: 0)
var granted = false
AVCaptureDevice.requestAccess(for: .audio) { g in granted = g; sem.signal() }
sem.wait()
if granted { print("granted") } else { print("denied") }
' 2>/dev/null
    echo ""
elif [ "$MIC_STATUS" = "3" ]; then
    echo "    Microphone access already granted."
elif [ "$MIC_STATUS" = "2" ]; then
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
