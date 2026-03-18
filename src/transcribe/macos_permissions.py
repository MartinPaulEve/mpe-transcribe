"""Check macOS accessibility permissions and warn if missing."""

import ctypes
import ctypes.util
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

_REMEDIATION = (
    "Open System Settings → Privacy & Security → Accessibility "
    "and add this app to the allowed list.\n\n"
    "If running from a terminal, add your terminal app "
    "(Terminal.app, iTerm2, etc.).\n\n"
    "If running as a service, add the transcribe binary "
    "(.venv/bin/transcribe inside the project folder).\n\n"
    "You may need to restart after granting permissions."
)


def is_accessibility_trusted() -> bool:
    """Return True if this process has accessibility permissions."""
    try:
        lib_path = ctypes.util.find_library("ApplicationServices")
        if lib_path is None:
            logger.debug("ApplicationServices not found")
            return True  # not macOS — assume OK
        lib = ctypes.cdll.LoadLibrary(lib_path)
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return lib.AXIsProcessTrusted()
    except (OSError, AttributeError):
        logger.debug("Could not call AXIsProcessTrusted", exc_info=True)
        return True  # can't determine — assume OK


def _is_interactive() -> bool:
    """Return True if stdin is connected to a terminal."""
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _show_alert_dialog(title: str, message: str):
    """Show a macOS modal alert dialog that blocks until dismissed."""
    script = (
        f'display alert "{title}" '
        f'message "{message}" '
        f"as critical "
        f'buttons {{"Open System Settings", "OK"}} '
        f'default button "Open System Settings"'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if "Open System Settings" in result.stdout:
            subprocess.run(
                [
                    "open",
                    "x-apple.systempreferences:"
                    "com.apple.preference.security"
                    "?Privacy_Accessibility",
                ],
                check=False,
            )
    except Exception:
        logger.debug("Failed to show alert dialog", exc_info=True)


def warn_if_not_trusted():
    """Check accessibility permissions and warn the user if missing.

    In a terminal session, logs a warning and sends a notification.
    When running as a service (no tty), shows a modal alert dialog
    that the user must dismiss.
    """
    if is_accessibility_trusted():
        return

    logger.warning(
        "Accessibility permissions not granted. "
        "The global hotkey will NOT work. %s",
        _REMEDIATION,
    )

    if _is_interactive():
        # Terminal: notification + stderr warning
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    'display notification '
                    '"Accessibility permissions required — '
                    'hotkey will not work. Check terminal for details." '
                    'with title "Transcribe"',
                ],
                check=False,
            )
        except Exception:
            pass
    else:
        # Service mode: big modal dialog the user can't miss
        _show_alert_dialog(
            "Transcribe — Accessibility Permission Required",
            _REMEDIATION.replace("\n\n", " "),
        )
