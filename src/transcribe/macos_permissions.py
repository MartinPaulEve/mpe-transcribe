"""Check macOS accessibility and microphone permissions."""

import ctypes
import ctypes.util
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

_ACCESSIBILITY_REMEDIATION = (
    "Open System Settings → Privacy & Security → Accessibility "
    "and toggle on 'Transcribe' (or add your terminal app if "
    "running from the terminal).\n\n"
    "You may need to restart the service after granting permissions."
)

_MICROPHONE_REMEDIATION = (
    "Microphone access must be granted before running as a "
    "service. Go to System Settings → Privacy & Security → "
    "Microphone and toggle on 'Transcribe'.\n\n"
    "If 'Transcribe' doesn't appear there yet, run the app "
    "from a terminal first (transcribe) and press the hotkey — "
    "macOS will show the microphone permission prompt."
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


def request_accessibility() -> bool:
    """Check accessibility and prompt the user if not trusted.

    Uses AXIsProcessTrustedWithOptions with kAXTrustedCheckOptionPrompt
    to show a macOS system dialog that guides the user to the correct
    System Settings pane. Returns True if already trusted.
    """
    try:
        lib_path = ctypes.util.find_library("ApplicationServices")
        if lib_path is None:
            return True

        lib = ctypes.cdll.LoadLibrary(lib_path)

        objc_path = ctypes.util.find_library("objc")
        if objc_path is None:
            return is_accessibility_trusted()
        objc = ctypes.cdll.LoadLibrary(objc_path)

        cf_path = ctypes.util.find_library("CoreFoundation")
        if cf_path is None:
            return is_accessibility_trusted()
        cf = ctypes.cdll.LoadLibrary(cf_path)

        # Set up objc runtime calls
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        # Build options dict: {kAXTrustedCheckOptionPrompt: True}
        # kAXTrustedCheckOptionPrompt is a CFString constant
        prompt_key = ctypes.c_void_p.in_dll(lib, "kAXTrustedCheckOptionPrompt")

        cf.CFBooleanGetValue.restype = ctypes.c_bool
        cf_true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")

        # Create a CFDictionary with one entry
        cf.CFDictionaryCreate.restype = ctypes.c_void_p
        cf.CFDictionaryCreate.argtypes = [
            ctypes.c_void_p,  # allocator
            ctypes.POINTER(ctypes.c_void_p),  # keys
            ctypes.POINTER(ctypes.c_void_p),  # values
            ctypes.c_long,  # count
            ctypes.c_void_p,  # key callbacks
            ctypes.c_void_p,  # value callbacks
        ]

        keys = (ctypes.c_void_p * 1)(prompt_key)
        values = (ctypes.c_void_p * 1)(cf_true)

        options = cf.CFDictionaryCreate(None, keys, values, 1, None, None)

        lib.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        lib.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]

        trusted = lib.AXIsProcessTrustedWithOptions(options)

        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease(options)

        if trusted:
            logger.info("Accessibility: already trusted.")
        else:
            logger.info("Accessibility: not trusted — macOS prompt shown.")
        return trusted
    except (OSError, AttributeError, ValueError):
        logger.debug(
            "Could not call AXIsProcessTrustedWithOptions",
            exc_info=True,
        )
        return is_accessibility_trusted()


def get_microphone_status() -> str:
    """Return the microphone authorization status.

    Uses the Objective-C runtime via ctypes to call
    AVCaptureDevice.authorizationStatusForMediaType: directly
    (no Swift compilation needed — instant).

    Returns one of: "authorized", "denied", "restricted",
    "not_determined", or "unknown".
    """
    try:
        objc_path = ctypes.util.find_library("objc")
        if objc_path is None:
            return "unknown"
        objc = ctypes.cdll.LoadLibrary(objc_path)

        avf = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/AVFoundation.framework/AVFoundation"
        )

        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        # objc_msgSend with signature: (id, SEL, id) -> NSInteger
        msg_send = ctypes.CFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(("objc_msgSend", objc))

        cls = objc.objc_getClass(b"AVCaptureDevice")
        sel = objc.sel_registerName(b"authorizationStatusForMediaType:")
        media_type = ctypes.c_void_p.in_dll(avf, "AVMediaTypeAudio")

        status = msg_send(cls, sel, media_type)
        return {
            0: "not_determined",
            1: "restricted",
            2: "denied",
            3: "authorized",
        }.get(status, "unknown")
    except Exception:
        logger.debug("Could not check microphone status", exc_info=True)
        return "unknown"


def request_microphone_access() -> bool:
    """Trigger the macOS microphone permission prompt.

    Opens a brief audio input stream via sounddevice, which causes
    macOS to show the microphone permission dialog on first access.
    Then re-checks the status to see if it was granted.

    Returns True if access was granted.
    """
    try:
        import sounddevice as sd

        # Opening an input stream triggers the macOS mic prompt.
        # CoreAudio blocks during device init until the user responds.
        stream = sd.InputStream(samplerate=16000, channels=1, dtype="float32")
        stream.start()
        stream.stop()
        stream.close()
        return get_microphone_status() == "authorized"
    except Exception:
        logger.debug("Could not request microphone access", exc_info=True)
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


def _warn_missing_permission(name: str, remediation: str, settings_url: str):
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
                    f"display notification "
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


def _running_under_launcher() -> bool:
    """Return True if the native launcher is handling permissions."""
    import os

    return os.environ.get("TRANSCRIBE_LAUNCHER") == "1"


def warn_if_not_trusted():
    """Check accessibility and microphone permissions on macOS.

    When running under the native launcher (TRANSCRIBE_LAUNCHER=1),
    skip checks — the launcher handles accessibility via CGEventTap,
    and microphone is checked at recording time, not at startup.
    The Python child has a different process identity so these checks
    would always report false negatives.

    In a terminal session, logs warnings and sends notifications.
    When running as a service without the launcher, shows modal
    alert dialogs that the user must dismiss.
    """
    if _running_under_launcher():
        logger.debug(
            "Running under native launcher — "
            "skipping permission checks (launcher owns TCC grants)"
        )
        return

    if not is_accessibility_trusted():
        if _is_interactive():
            logger.info("Requesting accessibility access...")
            granted = request_accessibility()
            if granted:
                logger.info("Accessibility already granted.")
            else:
                logger.warning(
                    "Accessibility not yet granted. "
                    "Grant it in the dialog or System Settings, "
                    "then restart transcribe."
                )
        else:
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

    _warn_missing_permission(
        "Microphone",
        _MICROPHONE_REMEDIATION,
        _MICROPHONE_SETTINGS_URL,
    )
