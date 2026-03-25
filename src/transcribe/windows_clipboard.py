import ctypes
import sys
import time

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

VK_CONTROL = 0x11
VK_V = 0x56
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_LWIN = 0x5B

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
else:
    _user32 = None
    _kernel32 = None


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ki", KEYBDINPUT),
    ]


def _make_key_input(vk, flags=0):
    return INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None
        ),
    )


class WindowsClipboard:
    def _get_clipboard(self) -> str | None:
        if not _user32.OpenClipboard(0):
            return None
        try:
            handle = _user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            ptr = _kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return ctypes.c_wchar_p(ptr).value
            finally:
                _kernel32.GlobalUnlock(handle)
        finally:
            _user32.CloseClipboard()

    def _set_clipboard(self, text: str):
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        _user32.OpenClipboard(0)
        try:
            _user32.EmptyClipboard()
            handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
            ptr = _kernel32.GlobalLock(handle)
            ctypes.memmove(ptr, encoded, len(encoded))
            _kernel32.GlobalUnlock(handle)
            _user32.SetClipboardData(CF_UNICODETEXT, handle)
        finally:
            _user32.CloseClipboard()

    def _simulate_ctrl_v(self):
        # Release ghost modifiers that may be held from the hotkey
        release = [
            _make_key_input(VK_SHIFT, KEYEVENTF_KEYUP),
            _make_key_input(VK_MENU, KEYEVENTF_KEYUP),
            _make_key_input(VK_LWIN, KEYEVENTF_KEYUP),
        ]
        # Ctrl+V sequence
        keys = [
            _make_key_input(VK_CONTROL),
            _make_key_input(VK_V),
            _make_key_input(VK_V, KEYEVENTF_KEYUP),
            _make_key_input(VK_CONTROL, KEYEVENTF_KEYUP),
        ]
        inputs = release + keys
        arr = (INPUT * len(inputs))(*inputs)
        _user32.SendInput(len(inputs), ctypes.byref(arr), ctypes.sizeof(INPUT))

    def paste_text(self, text: str):
        previous = self._get_clipboard()
        self._set_clipboard(text)
        time.sleep(0.05)
        self._simulate_ctrl_v()
        time.sleep(0.2)
        if previous is not None:
            self._set_clipboard(previous)
