#!/usr/bin/env bash
set -euo pipefail

echo "==> Uninstalling transcribe"

# Stop and disable service
systemctl --user stop transcribe.service 2>/dev/null || true
systemctl --user disable transcribe.service 2>/dev/null || true

# Remove files
rm -f "${HOME}/.config/systemd/user/transcribe.service"
rm -f "${HOME}/.local/share/applications/transcribe.desktop"
rm -f "${HOME}/.local/share/icons/hicolor/scalable/apps/transcribe.svg"

systemctl --user daemon-reload
update-desktop-database "${HOME}/.local/share/applications" 2>/dev/null || true

echo "==> Uninstalled"
