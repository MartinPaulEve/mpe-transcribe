#!/usr/bin/env bash
# Install mpe-transcribe as a macOS launchd agent (auto-start on login).
#
# Creates a lightweight Transcribe.app wrapper bundle so that macOS TCC
# can persistently track permissions (accessibility + microphone) via
# a stable CFBundleIdentifier — no more re-prompting after reboot.
#
# The launchd plist uses `open -W -a Transcribe.app` so that macOS
# designates the .app as the "responsible process" for TCC checks.
# The launcher runs Python as a *child* process (not exec) so the
# .app's process stays alive and retains its TCC identity.
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

# Kill any running instance of the app
killall -9 "$APP_NAME" 2>/dev/null || true

# ── Build the .app bundle ─────────────────────────────────────────
echo "==> Building $APP_NAME.app..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Info.plist — gives the app a stable bundle identity for TCC.
# NSMicrophoneUsageDescription is required for the mic permission
# dialog.  LSBackgroundOnly keeps it out of the Dock.
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
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSBackgroundOnly</key>
    <true/>
    <key>LSUIElement</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Transcribe needs microphone access to record speech for transcription.</string>
</dict>
</plist>
INFOPLIST

# Launcher script — runs Python as a CHILD process (not exec).
# This keeps the .app's shell process alive as the "responsible
# process" for macOS TCC, so accessibility and microphone grants
# are attributed to Transcribe.app (not to the Python binary).
# SIGTERM/SIGINT are forwarded to the child Python process.
cat > "$APP_DIR/Contents/MacOS/transcribe-launcher" <<'LAUNCHER_HEAD'
#!/bin/bash
LAUNCHER_HEAD

cat >> "$APP_DIR/Contents/MacOS/transcribe-launcher" <<LAUNCHER_BODY
export PYTHONPATH="$SCRIPT_DIR/src:\${PYTHONPATH:-}"

# Run Python as a child process — do NOT exec.
"$PYTHON_REAL" -m transcribe "\$@" &
CHILD=\$!

# Forward termination signals to the child process.
cleanup() {
    kill -TERM "\$CHILD" 2>/dev/null
    wait "\$CHILD" 2>/dev/null
}
trap cleanup TERM INT HUP

# Wait for the child to exit.
wait "\$CHILD"
LAUNCHER_BODY
chmod +x "$APP_DIR/Contents/MacOS/transcribe-launcher"

# Ad-hoc codesign the .app bundle so macOS accepts it.
# NOTE: We do NOT codesign the Python binary — that would
# invalidate any existing TCC grants the user has set up.
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

# Accessibility: prompt the user to grant it.
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
# The plist uses `open -W -a Transcribe.app` instead of running
# the launcher directly. This makes macOS treat Transcribe.app as
# the "responsible process" for TCC — permissions granted to the
# app persist across reboots via the stable CFBundleIdentifier.
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
        <string>/usr/bin/open</string>
        <string>-W</string>
        <string>-a</string>
        <string>$APP_DIR</string>
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
