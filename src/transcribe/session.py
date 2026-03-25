import os
import platform


def detect_session() -> str:
    """Detect whether the session is macOS, Windows, Wayland, or X11.

    Returns "macos", "windows", "wayland", or "x11".
    """
    if platform.system() == "Darwin":
        return "macos"
    if platform.system() == "Windows":
        return "windows"
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    if session_type == "wayland":
        return "wayland"
    if session_type == "x11":
        return "x11"
    if os.environ.get("WAYLAND_DISPLAY", ""):
        return "wayland"
    return "x11"
