#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UV_BIN="$(command -v uv)"

echo "==> Installing transcribe from ${PROJECT_DIR}"

if [[ -z "$UV_BIN" ]]; then
    echo "ERROR: uv not found in PATH." >&2
    exit 1
fi

# Ensure venv and deps are up to date (including platform-specific extras)
echo "==> Syncing dependencies..."
(cd "$PROJECT_DIR" && uv sync --extra linux)

# Build the ExecStart command: uv run with linux extras for platform deps
EXEC="${UV_BIN} run --extra linux --project ${PROJECT_DIR} transcribe"

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

UV_DIR="$(dirname "${UV_BIN}")"
sed \
    -e "s|ExecStart=PLACEHOLDER|ExecStart=${EXEC}|" \
    -e "s|WorkingDirectory=WORKDIR_PLACEHOLDER|WorkingDirectory=${PROJECT_DIR}|" \
    -e "s|PATH_PLACEHOLDER|${UV_DIR}|" \
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
