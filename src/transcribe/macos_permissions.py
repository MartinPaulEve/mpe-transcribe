"""Check macOS accessibility and microphone permissions."""

import ctypes
import ctypes.util
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

_ACCESSIBILITY_REMEDIATION = (
    "Open System Settings → Privacy & Security → Accessibility "
    "and add this app to the allowed list.\n\n"
    "If running from a terminal, add your terminal app "
    "(Terminal.app, iTerm2, etc.).\n\n"
    "If running as a service, add the transcribe binary "
    "(.venv/bin/transcribe inside the project folder).\n\n"
    "You may need to restart after granting permissions."
)

_MICROPHONE_REMEDIATION = (
    "Open System Settings → Privacy & Security → Microphone "
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


def is_microphone_authorized() -> bool:
    """Return True if this process has microphone permissions.

    Uses AVFoundation via a swift subprocess to check the
    authorization status.  Returns 3 (authorized) on success.
    """
    try:
        result = subprocess.run(
            [
                "swift",
                "-e",
                "import AVFoundation; "
                "print(AVCaptureDevice.authorizationStatus("
                "for: .audio).rawValue)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = result.stdout.strip()
        # 0=notDetermined, 1=restricted, 2=denied, 3=authorized
        if status == "3":
            return True
        if status in ("1", "2"):
            return False
        # notDetermined (0) or unexpected — assume OK so macOS
        # can show its own prompt on first use
        return True
    except Exception:
        logger.debug("Could not check microphone status", exc_info=True)
        return True  # can't determine — assume OK


def _is_interactive() -> bool:
    """Return True if stdin is connected to a terminal."""
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _show_alert_dialog(title: str, message: str, settings_url: str):
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
                ["open", settings_url],
                check=False,
            )
    except Exception:
        logger.debug("Failed to show alert dialog", exc_info=True)


_ACCESSIBILITY_SETTINGS_URL = (
    "x-apple.systempreferences:"
    "com.apple.preference.security"
    "?Privacy_Accessibility"
)

_MICROPHONE_SETTINGS_URL = (
    "x-apple.systempreferences:"
    "com.apple.preference.security"
    "?Privacy_Microphone"
)


def _warn_missing_permission(
    name: str, remediation: str, settings_url: str
):
    """Warn about a missing permission via notification or dialog."""
    logger.warning(
        "%s permissions not granted. %s",
        name,
        remediation,
    )

    if _is_interactive():
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification '
                    f'"{name} permissions required — '
                    f'check terminal for details." '
                    f'with title "Transcribe"',
                ],
                check=False,
            )
        except Exception:
            pass
    else:
        _show_alert_dialog(
            f"Transcribe — {name} Permission Required",
            remediation.replace("\n\n", " "),
            settings_url,
        )


def warn_if_not_trusted():
    """Check accessibility and microphone permissions on macOS.

    In a terminal session, logs warnings and sends notifications.
    When running as a service (no tty), shows modal alert dialogs
    that the user must dismiss.
    """
    if not is_accessibility_trusted():
        _warn_missing_permission(
            "Accessibility",
            _ACCESSIBILITY_REMEDIATION,
            _ACCESSIBILITY_SETTINGS_URL,
        )

    if not is_microphone_authorized():
        _warn_missing_permission(
            "Microphone",
            _MICROPHONE_REMEDIATION,
            _MICROPHONE_SETTINGS_URL,
        )
