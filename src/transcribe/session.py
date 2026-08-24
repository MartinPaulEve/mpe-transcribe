import os
import platform


def _wayland_socket_exists() -> bool:
    """True if the compositor's socket is present in the runtime dir.

    Environment variables lie in stale shells (tmux/byobu panes keep
    the env of the session that started the server); the live socket
    on disk is the ground truth.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
    if not runtime_dir:
        runtime_dir = f"/run/user/{os.getuid()}"
    try:
        entries = os.listdir(runtime_dir)
    except OSError:
        return False
    return any(
        name.startswith("wayland-") and not name.endswith(".lock")
        for name in entries
    )


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
    if _wayland_socket_exists():
        return "wayland"
    return "x11"
