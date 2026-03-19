import ctypes
import ctypes.util
import subprocess
import time

# --- CoreGraphics via ctypes for Cmd+V keystroke ---
_cg_path = ctypes.util.find_library("CoreGraphics")
_cg = ctypes.cdll.LoadLibrary(_cg_path) if _cg_path else None

if _cg:
    _cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    _cg.CGEventCreateKeyboardEvent.argtypes = [
        ctypes.c_void_p,  # source (NULL)
        ctypes.c_uint16,  # virtualKey
        ctypes.c_bool,    # keyDown
    ]
    _cg.CGEventSetFlags.restype = None
    _cg.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    _cg.CGEventPost.restype = None
    _cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]

    _cf_path = ctypes.util.find_library("CoreFoundation")
    _cf = ctypes.cdll.LoadLibrary(_cf_path)
    _cf.CFRelease.restype = None
    _cf.CFRelease.argtypes = [ctypes.c_void_p]

_kCGEventFlagMaskCommand = 0x00100000
_kCGHIDEventTap = 0  # post at HID level
_kVK_ANSI_V = 0x09


def _post_cmd_v():
    """Simulate Cmd+V keystroke via CGEventPost."""
    if not _cg:
        raise RuntimeError("CoreGraphics not available")

    # Key down
    down = _cg.CGEventCreateKeyboardEvent(None, _kVK_ANSI_V, True)
    _cg.CGEventSetFlags(down, _kCGEventFlagMaskCommand)
    _cg.CGEventPost(_kCGHIDEventTap, down)
    _cf.CFRelease(down)

    time.sleep(0.01)

    # Key up
    up = _cg.CGEventCreateKeyboardEvent(None, _kVK_ANSI_V, False)
    _cg.CGEventSetFlags(up, _kCGEventFlagMaskCommand)
    _cg.CGEventPost(_kCGHIDEventTap, up)
    _cf.CFRelease(up)


class MacOSClipboard:
    def _get_clipboard(self) -> str | None:
        result = subprocess.run(
            ["pbpaste"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def _set_clipboard(self, text: str):
        subprocess.run(
            ["pbcopy"],
            input=text,
            text=True,
            check=True,
        )

    def paste_text(self, text: str):
        previous = self._get_clipboard()
        self._set_clipboard(text)
        time.sleep(0.05)
        _post_cmd_v()
        time.sleep(0.2)
        if previous is not None:
            self._set_clipboard(previous)
