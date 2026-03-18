import logging

from transcribe.session import detect_session

logger = logging.getLogger(__name__)


def create_hotkey_listener(callback, modifiers: set[str], key: str):
    """Create a hotkey listener for the current session type."""
    session = detect_session()
    logger.info("Session type: %s", session)
    if session == "macos":
        from transcribe.macos_hotkey import MacOSHotkeyListener

        return MacOSHotkeyListener(
            callback, modifiers=modifiers, key=key
        )
    elif session == "wayland":
        from transcribe.wayland_hotkey import WaylandHotkeyListener

        return WaylandHotkeyListener(
            callback, modifiers=modifiers, key=key
        )
    else:
        from transcribe.hotkey import HotkeyListener

        return HotkeyListener(callback, modifiers=modifiers, key=key)


def create_clipboard():
    """Create a clipboard handler for the current session type."""
    session = detect_session()
    if session == "macos":
        from transcribe.macos_clipboard import MacOSClipboard

        return MacOSClipboard()
    elif session == "wayland":
        from transcribe.wayland_clipboard import WaylandClipboard

        return WaylandClipboard()
    else:
        from transcribe.clipboard import Clipboard

        return Clipboard()


def create_transcriber(model_name: str):
    """Create a transcriber for the current session type."""
    session = detect_session()
    if session == "macos":
        from transcribe.macos_transcriber import MacOSTranscriber

        return MacOSTranscriber(model_name=model_name)
    else:
        from transcribe.transcriber import Transcriber

        return Transcriber(model_name=model_name)


def create_notifier():
    """Create a notifier for the current session type."""
    session = detect_session()
    if session == "macos":
        from transcribe.macos_notifier import MacOSNotifier

        return MacOSNotifier()
    else:
        from transcribe.notifier import AppNotifier

        return AppNotifier()
