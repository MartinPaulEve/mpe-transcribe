#!/usr/bin/env bash
set -euo pipefail

# Install transcribe in CLIENT mode: hotkey + paste only.
# The heavy transcription stack (models, GPU, sounddevice) is NOT
# installed — a transcribe host on the network does that work.

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UV_BIN="$(command -v uv)"

echo "==> Installing transcribe (client mode) from ${PROJECT_DIR}"

if [[ -z "$UV_BIN" ]]; then
    echo "ERROR: uv not found in PATH." >&2
    exit 1
fi

OS="$(uname -s)"
case "$OS" in
    Linux)  EXTRA="client-linux" ;;
    Darwin) EXTRA="client-macos" ;;
    *)
        echo "ERROR: unsupported platform: $OS" >&2
        exit 1
        ;;
esac

echo "==> Syncing client-only dependencies (--extra ${EXTRA})..."
(cd "$PROJECT_DIR" && uv sync --extra "$EXTRA")

EXEC="${UV_BIN} run --extra ${EXTRA} --project ${PROJECT_DIR} transcribe --client"

# --- Key / config directory ---
CONF_DIR="${HOME}/.config/transcribe"
mkdir -p "$CONF_DIR"
if [[ ! -f "${CONF_DIR}/env" ]]; then
    cat > "${CONF_DIR}/env" <<'EOF'
# Pre-shared key for transcribe network mode.
# Generate one on the host with:  transcribe keygen
# Then set the SAME key on host and clients.
#TRANSCRIBE_PSK=<base64 32-byte key>
EOF
    chmod 600 "${CONF_DIR}/env"
    echo "==> Created ${CONF_DIR}/env — add your TRANSCRIBE_PSK there."
fi

if [[ "$OS" == "Linux" ]]; then
    # --- Systemd user service ---
    SERVICE_DIR="${HOME}/.config/systemd/user"
    mkdir -p "$SERVICE_DIR"

    UV_DIR="$(dirname "${UV_BIN}")"
    sed \
        -e "s|ExecStart=PLACEHOLDER|ExecStart=${EXEC}|" \
        -e "s|WorkingDirectory=WORKDIR_PLACEHOLDER|WorkingDirectory=${PROJECT_DIR}|" \
        -e "s|PATH_PLACEHOLDER|${UV_DIR}|" \
        "${PROJECT_DIR}/assets/transcribe-client.service" \
        > "${SERVICE_DIR}/transcribe-client.service"

    systemctl --user daemon-reload
    systemctl --user enable transcribe-client.service

    echo "==> Systemd user service installed and enabled"
    echo "    It will auto-start when your graphical session begins."
    echo ""
    echo "    Manual control:"
    echo "      systemctl --user start transcribe-client"
    echo "      systemctl --user stop transcribe-client"
    echo "      systemctl --user status transcribe-client"
    echo "      journalctl --user -u transcribe-client -f"
else
    # --- launchd user agent (macOS) ---
    AGENT_DIR="${HOME}/Library/LaunchAgents"
    PLIST="${AGENT_DIR}/gd.eve.transcribe-client.plist"
    mkdir -p "$AGENT_DIR"

    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>gd.eve.transcribe-client</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-lc</string>
        <string>source ${CONF_DIR}/env 2>/dev/null; export TRANSCRIBE_PSK; exec ${EXEC}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
</dict>
</plist>
EOF

    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"

    echo "==> launchd agent installed: ${PLIST}"
    echo "    Manual control:"
    echo "      launchctl unload ${PLIST}"
    echo "      launchctl load ${PLIST}"
fi

echo ""
echo "==> Client installation complete!"
echo "    1. Generate a key on the HOST:   transcribe keygen"
echo "    2. Put it in ${CONF_DIR}/env as  TRANSCRIBE_PSK=<key>"
echo "    3. Point [tool.transcribe.network] server_host at the host"
echo "       (see docs/NETWORK.md)."
