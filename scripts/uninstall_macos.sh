#!/usr/bin/env bash
# Uninstall mpe-transcribe launchd agent.
set -euo pipefail

PLIST_NAME="com.mpe.transcribe"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

APP_DIR="$HOME/Applications/Transcribe.app"

launchctl stop "$PLIST_NAME" 2>/dev/null || true

if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "Removed launchd agent: $PLIST_PATH"
else
    echo "No launchd agent found at $PLIST_PATH"
fi

if [ -d "$APP_DIR" ]; then
    rm -rf "$APP_DIR"
    echo "Removed app bundle: $APP_DIR"
fi
