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
    "Microphone access must be granted before running as a "
    "service. Run 'uv run transcribe' once from the terminal — "
    "macOS will show a permission prompt. Grant access, then "
    "Ctrl+C and start the service.\n\n"
    "If you previously denied the prompt, go to "
    "System Settings → Privacy & Security → Microphone "
    "and toggle access on for your terminal app."
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


def get_microphone_status() -> str:
    """Return the microphone authorization status.

    Returns one of: "authorized", "denied", "restricted",
    "not_determined", or "unknown".
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
        return {
            "0": "not_determined",
            "1": "restricted",
            "2": "denied",
            "3": "authorized",
        }.get(status, "unknown")
    except Exception:
        logger.debug("Could not check microphone status", exc_info=True)
        return "unknown"


def request_microphone_access() -> bool:
    """Trigger the macOS microphone permission prompt.

    This blocks until the user responds to the system dialog.
    Returns True if access was granted.
    """
    try:
        result = subprocess.run(
            [
                "swift",
                "-e",
                "import AVFoundation; "
                "import Darwin; "
                "let sem = DispatchSemaphore(value: 0); "
                "var granted = false; "
                "AVCaptureDevice.requestAccess(for: .audio) { g in "
                "granted = g; sem.signal() }; "
                "sem.wait(); "
                "print(granted)",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout.strip() == "true"
    except Exception:
        logger.debug(
            "Could not request microphone access", exc_info=True
        )
        return False


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

    If microphone status is not yet determined and we are running
    interactively, triggers the macOS permission prompt so the user
    can grant access right away.
    """
    if not is_accessibility_trusted():
        _warn_missing_permission(
            "Accessibility",
            _ACCESSIBILITY_REMEDIATION,
            _ACCESSIBILITY_SETTINGS_URL,
        )

    mic_status = get_microphone_status()
    if mic_status == "authorized" or mic_status == "unknown":
        return

    if mic_status == "not_determined":
        if _is_interactive():
            logger.info("Requesting microphone access...")
            granted = request_microphone_access()
            if granted:
                logger.info("Microphone access granted.")
                return
            logger.warning("Microphone access was denied.")
        # Not interactive + not_determined: service can't prompt
        # Fall through to warn

    _warn_missing_permission(
        "Microphone",
        _MICROPHONE_REMEDIATION,
        _MICROPHONE_SETTINGS_URL,
    )
