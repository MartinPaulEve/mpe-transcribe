import os


def detect_session() -> str:
    """Detect whether the session is Wayland or X11.

    Returns "wayland" or "x11".
    """
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    if session_type == "wayland":
        return "wayland"
    if session_type == "x11":
        return "x11"
    if os.environ.get("WAYLAND_DISPLAY", ""):
        return "wayland"
    return "x11"
