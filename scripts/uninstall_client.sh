#!/usr/bin/env bash
set -euo pipefail

echo "==> Uninstalling transcribe client"

OS="$(uname -s)"

if [[ "$OS" == "Linux" ]]; then
    systemctl --user stop transcribe-client.service 2>/dev/null || true
    systemctl --user disable transcribe-client.service 2>/dev/null || true
    rm -f "${HOME}/.config/systemd/user/transcribe-client.service"
    systemctl --user daemon-reload
elif [[ "$OS" == "Darwin" ]]; then
    PLIST="${HOME}/Library/LaunchAgents/gd.eve.transcribe-client.plist"
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
fi

# The key file in ~/.config/transcribe/env is left in place —
# remove it yourself if you no longer need the shared key.

echo "==> Uninstalled"
