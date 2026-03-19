#!/usr/bin/env bash
# Install mpe-transcribe as a macOS launchd agent (auto-start on login).
#
# Creates a Transcribe.app bundle with a native Mach-O executable so
# that macOS TCC can persistently track permissions (accessibility +
# microphone) via a stable CFBundleIdentifier.
#
# Apple's TCC requires a *native* (Mach-O) CFBundleExecutable — shell
# scripts and Python interpreters do not get stable TCC identity.
# We compile a C launcher that monitors the global hotkey via
# CGEventTap (using the .app's accessibility grant) and signals the
# Python child with SIGUSR1 when the hotkey is pressed.
set -euo pipefail

PLIST_NAME="com.mpe.transcribe"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$PLIST_NAME.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

APP_NAME="Transcribe"
APP_DIR="$HOME/Applications/$APP_NAME.app"
BUNDLE_ID="com.mpe.transcribe"
LAUNCHER_SRC="$SCRIPT_DIR/scripts/transcribe_launcher.c"

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

# Verify C compiler is available (Xcode CLT)
if ! command -v cc &>/dev/null; then
    echo "Error: C compiler (cc) not found."
    echo "Install Xcode Command Line Tools:  xcode-select --install"
    exit 1
fi

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
    <key>CFBundleIconFile</key>
    <string>Transcribe</string>
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

# Read hotkey config and convert to CGEventTap values (keycode + modifiers).
echo "==> Reading hotkey configuration..."
read HOTKEY_KEYCODE HOTKEY_MODIFIERS <<< $("$PYTHON" -c "
from transcribe.config import load_config, hotkey_to_cg_values
cfg = load_config()
kc, mf = hotkey_to_cg_values(cfg['hotkey'])
print(f'0x{kc:02x} 0x{mf:06x}')
" 2>/dev/null || echo "0x27 0x120000")  # fallback: Cmd+Shift+'

echo "    Hotkey keycode=$HOTKEY_KEYCODE modifiers=$HOTKEY_MODIFIERS"

# Compile the native Mach-O launcher.
# The launcher monitors the global hotkey via CGEventTap (which gets
# accessibility from the .app's TCC grant) and signals the Python
# child with SIGUSR1 when the hotkey is pressed.
echo "==> Compiling native launcher..."
cc -O2 -o "$APP_DIR/Contents/MacOS/transcribe-launcher" \
    -DPYTHON_BIN="$PYTHON_REAL" \
    -DPYTHON_PATH="$SCRIPT_DIR/src" \
    -DHOTKEY_KEYCODE="$HOTKEY_KEYCODE" \
    -DHOTKEY_MODIFIERS="$HOTKEY_MODIFIERS" \
    -framework CoreFoundation \
    -framework CoreGraphics \
    "$LAUNCHER_SRC"

echo "    Compiled: $APP_DIR/Contents/MacOS/transcribe-launcher"

# ── Generate .icns icon ──────────────────────────────────────────
# Converts the SVG icon to .icns so the app has a proper icon in
# macOS permission dialogs (Privacy & Security → Microphone, etc.)
# This MUST happen before codesigning — adding files after signing
# invalidates the signature and breaks TCC trust.
ICON_SVG="$SCRIPT_DIR/assets/transcribe.svg"
ICON_ICNS="$APP_DIR/Contents/Resources/Transcribe.icns"

if [ -f "$ICON_SVG" ]; then
    echo "==> Generating app icon..."
    ICON_TMP=$(mktemp -d)
    ICONSET_DIR="$ICON_TMP/Transcribe.iconset"
    mkdir -p "$ICONSET_DIR"

    # Render SVG to a large PNG via QuickLook
    qlmanage -t -s 1024 -o "$ICON_TMP" "$ICON_SVG" &>/dev/null
    ICON_PNG="$ICON_TMP/transcribe.svg.png"

    if [ -f "$ICON_PNG" ]; then
        # Create all required icon sizes
        for size in 16 32 128 256 512; do
            sips -z "$size" "$size" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}.png" &>/dev/null
            double=$((size * 2))
            sips -z "$double" "$double" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" &>/dev/null
        done

        iconutil -c icns -o "$ICON_ICNS" "$ICONSET_DIR" 2>/dev/null && \
            echo "    Icon installed: $ICON_ICNS" || \
            echo "    Warning: could not generate .icns (non-fatal)"
    else
        echo "    Warning: could not render SVG to PNG (non-fatal)"
    fi

    rm -rf "$ICON_TMP"
fi

# Ad-hoc codesign the .app bundle so macOS accepts it.
# NOTE: We do NOT codesign the Python binary — that would
# invalidate any existing TCC grants the user has set up.
echo "==> Codesigning $APP_NAME.app..."
codesign -s - -f --deep "$APP_DIR" 2>/dev/null || true

echo "    Installed: $APP_DIR"

# ── Permissions guidance ──────────────────────────────────────────
# The launcher handles hotkey monitoring via CGEventTap, which needs
# the .app bundle to have Accessibility.  Microphone is requested at
# runtime when the user first records.
# NOTE: We can't programmatically request accessibility for the .app
# from Python — AXIsProcessTrustedWithOptions would register the
# Python binary, not the .app.  The user must add it manually.

# ── Install the launchd agent ─────────────────────────────────────
# The plist runs the native launcher binary directly.  The launcher
# monitors the hotkey via CGEventTap (with the .app's TCC grant) and
# forwards SIGTERM to the Python child for clean shutdown.
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
