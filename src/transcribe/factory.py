import logging

from transcribe.session import detect_session

logger = logging.getLogger(__name__)


def create_hotkey_listener(callback, modifiers: set[str], key: str):
    """Create a hotkey listener for the current session type."""
    session = detect_session()
    logger.info("Session type: %s", session)
    if session == "wayland":
        from transcribe.wayland_hotkey import WaylandHotkeyListener

        return WaylandHotkeyListener(callback, modifiers=modifiers, key=key)
    else:
        from transcribe.hotkey import HotkeyListener

        return HotkeyListener(callback, modifiers=modifiers, key=key)


def create_clipboard():
    """Create a clipboard handler for the current session type."""
    session = detect_session()
    if session == "wayland":
        from transcribe.wayland_clipboard import WaylandClipboard

        return WaylandClipboard()
    else:
        from transcribe.clipboard import Clipboard

        return Clipboard()
