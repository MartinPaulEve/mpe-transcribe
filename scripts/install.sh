#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="${PROJECT_DIR}/.venv/bin"
EXEC="${VENV_BIN}/transcribe"

echo "==> Installing transcribe from ${PROJECT_DIR}"

# Ensure venv and deps are up to date
echo "==> Syncing dependencies..."
(cd "$PROJECT_DIR" && uv sync)

# Verify the entry point exists
if [[ ! -x "$EXEC" ]]; then
    echo "ERROR: ${EXEC} not found. Run 'uv sync' first." >&2
    exit 1
fi

# --- Desktop entry (launcher icon) ---
DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"

mkdir -p "$DESKTOP_DIR" "$ICON_DIR"

cp "${PROJECT_DIR}/assets/transcribe.svg" "${ICON_DIR}/transcribe.svg"

sed \
    -e "s|Exec=PLACEHOLDER|Exec=${EXEC}|" \
    "${PROJECT_DIR}/assets/transcribe.desktop" \
    > "${DESKTOP_DIR}/transcribe.desktop"

# Update icon cache (best-effort)
gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo "==> Desktop entry installed: ${DESKTOP_DIR}/transcribe.desktop"

# --- Systemd user service (daemon) ---
SERVICE_DIR="${HOME}/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

sed \
    -e "s|ExecStart=PLACEHOLDER|ExecStart=${EXEC}|" \
    "${PROJECT_DIR}/assets/transcribe.service" \
    > "${SERVICE_DIR}/transcribe.service"

systemctl --user daemon-reload
systemctl --user enable transcribe.service

echo "==> Systemd user service installed and enabled"
echo "    It will auto-start when your graphical session begins."
echo ""
echo "    Manual control:"
echo "      systemctl --user start transcribe"
echo "      systemctl --user stop transcribe"
echo "      systemctl --user status transcribe"
echo "      journalctl --user -u transcribe -f"
echo ""
echo "==> Installation complete!"
