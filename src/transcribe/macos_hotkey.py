import threading
import time

from pynput.keyboard import GlobalHotKeys

_DEBOUNCE_SECONDS = 0.3

_MODIFIER_MAP = {
    "ctrl": "<ctrl>",
    "shift": "<shift>",
    "alt": "<alt>",
    "super": "<cmd>",
}


class MacOSHotkeyListener:
    def __init__(self, callback, modifiers: set[str] = None, key: str = None):
        self._callback = callback
        self._modifiers = modifiers or {"ctrl", "shift"}
        self._key = key or ";"
        self._thread = None
        self._running = False
        self._last_press = 0.0
        self._hotkeys = None

    def _build_hotkey_string(self) -> str:
        """Build a pynput-style hotkey combination string."""
        parts = []
        for mod in sorted(self._modifiers):
            token = _MODIFIER_MAP.get(mod)
            if token is None:
                raise ValueError(f"Unknown modifier: {mod!r}")
            parts.append(token)
        parts.append(self._key)
        return "+".join(parts)

    def _on_hotkey(self):
        """Called when the hotkey combination is detected."""
        now = time.monotonic()
        if now - self._last_press < _DEBOUNCE_SECONDS:
            return
        self._last_press = now
        threading.Thread(target=self._callback, daemon=True).start()

    def _run(self):
        combo = self._build_hotkey_string()
        self._hotkeys = GlobalHotKeys({combo: self._on_hotkey})
        self._hotkeys.daemon = True
        self._hotkeys.start()
        while self._running:
            time.sleep(0.1)
        self._hotkeys.stop()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._hotkeys is not None:
            self._hotkeys.stop()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
