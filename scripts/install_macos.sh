#!/usr/bin/env bash
# Install mpe-transcribe as a macOS launchd agent (auto-start on login).
#
# Creates a lightweight Transcribe.app wrapper bundle so that macOS TCC
# can persistently track permissions (accessibility + microphone) via
# a stable CFBundleIdentifier — no more re-prompting after reboot.
set -euo pipefail

PLIST_NAME="com.mpe.transcribe"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$PLIST_NAME.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

APP_NAME="Transcribe"
APP_DIR="$HOME/Applications/$APP_NAME.app"
BUNDLE_ID="com.mpe.transcribe"

# ── Locate Python & venv ──────────────────────────────────────────
PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "Error: Python venv not found at $PYTHON"
    echo "Install first:  uv pip install -e '.[macos]'"
    exit 1
fi

PYTHON_REAL=$("$PYTHON" -c "import sys; print(sys.executable)" 2>/dev/null || echo "$PYTHON")

# Verify transcribe is importable
"$PYTHON" -c "import transcribe" 2>/dev/null || {
    echo "Error: transcribe package not installed."
    echo "Install first:  uv pip install -e '.[macos]'"
    exit 1
}

# ── Unload previous service (if any) ─────────────────────────────
launchctl stop "$PLIST_NAME" 2>/dev/null || true
launchctl unload "$PLIST_PATH" 2>/dev/null || true

# ── Build the .app bundle ─────────────────────────────────────────
echo "==> Building $APP_NAME.app..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Info.plist — gives the app a stable bundle identity for TCC
cat > "$APP_DIR/Contents/Info.plist" <<INFOPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleExecutable</key>
    <string>transcribe-launcher</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>LSBackgroundOnly</key>
    <true/>
    <key>LSUIElement</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Transcribe needs microphone access to record speech for transcription.</string>
</dict>
</plist>
INFOPLIST

# Launcher script — exec replaces the shell so the Python process
# inherits the .app's bundle identity (and its TCC grants).
cat > "$APP_DIR/Contents/MacOS/transcribe-launcher" <<LAUNCHER
#!/bin/bash
export PYTHONPATH="$SCRIPT_DIR/src:\${PYTHONPATH:-}"
exec "$PYTHON_REAL" -m transcribe "\$@"
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/transcribe-launcher"

# Ad-hoc codesign the .app so macOS accepts it
echo "==> Codesigning $APP_NAME.app..."
codesign -s - -f --deep "$APP_DIR" 2>/dev/null || true

echo "    Installed: $APP_DIR"

# ── Request permissions interactively ─────────────────────────────
# Microphone: must be triggered interactively before running as a
# service, because launchd agents cannot show TCC prompts.
echo "==> Checking microphone permissions..."
MIC_STATUS=$("$PYTHON" -c "from transcribe.macos_permissions import get_microphone_status; print(get_microphone_status())" 2>/dev/null || echo "unknown")

if [ "$MIC_STATUS" = "not_determined" ]; then
    echo "==> Requesting microphone access (grant in the system dialog)..."
    "$PYTHON" -c "
from transcribe.macos_permissions import request_microphone_access
granted = request_microphone_access()
print('Microphone access ' + ('granted' if granted else 'denied'))
" 2>/dev/null
    echo ""
elif [ "$MIC_STATUS" = "authorized" ]; then
    echo "    Microphone access already granted."
elif [ "$MIC_STATUS" = "denied" ] || [ "$MIC_STATUS" = "restricted" ]; then
    echo ""
    echo "WARNING: Microphone access was previously denied."
    echo "  Go to System Settings → Privacy & Security → Microphone"
    echo "  and toggle access on for '$APP_NAME' (or your terminal app)."
    echo "  Alternatively, reset with:  tccutil reset Microphone"
    echo "  Then re-run this install script."
    echo ""
fi

# Accessibility: prompt the user to grant it
echo "==> Checking accessibility permissions..."
"$PYTHON" -c "
from transcribe.macos_permissions import request_accessibility
trusted = request_accessibility()
if trusted:
    print('    Accessibility already granted.')
else:
    print()
    print('    macOS will prompt you to grant Accessibility access.')
    print('    Add \"$APP_NAME\" in System Settings → Privacy & Security → Accessibility')
    print()
" 2>/dev/null

# ── Install the launchd agent ─────────────────────────────────────
echo "==> Installing launchd agent..."
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
        <string>$APP_DIR/Contents/MacOS/transcribe-launcher</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/transcribe.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/transcribe.stderr.log</string>
</dict>
</plist>
PLIST

launchctl load "$PLIST_PATH" 2>/dev/null || true
launchctl start "$PLIST_NAME" 2>/dev/null || true

echo ""
echo "==> Installation complete!"
echo ""
echo "  $APP_NAME.app is installed at: $APP_DIR"
echo "  The service will start automatically on login."
echo ""
echo "  If this is your first install, grant these permissions in"
echo "  System Settings → Privacy & Security:"
echo ""
echo "    Accessibility  →  add '$APP_NAME' (or toggle it on)"
echo "    Microphone     →  toggle '$APP_NAME' on"
echo ""
echo "  After granting permissions, restart the service:"
echo "    launchctl stop $PLIST_NAME && launchctl start $PLIST_NAME"
echo ""
echo "  Logs:  /tmp/transcribe.std{out,err}.log"
