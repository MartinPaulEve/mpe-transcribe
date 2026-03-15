import logging
import selectors
import threading
import time

import evdev
from evdev import ecodes

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 0.3

# Map modifier names to sets of evdev key codes (left + right variants)
_MODIFIER_KEYS = {
    "ctrl": {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL},
    "shift": {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT},
    "alt": {ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT},
    "super": {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA},
}

# Map symbol characters to evdev key names
_SYMBOL_MAP = {
    ";": "KEY_SEMICOLON",
    "'": "KEY_APOSTROPHE",
    ",": "KEY_COMMA",
    ".": "KEY_DOT",
    "/": "KEY_SLASH",
    "\\": "KEY_BACKSLASH",
    "[": "KEY_LEFTBRACE",
    "]": "KEY_RIGHTBRACE",
    "-": "KEY_MINUS",
    "=": "KEY_EQUAL",
    "`": "KEY_GRAVE",
}


def _resolve_key_code(key_name: str) -> int:
    """Resolve a key name to an evdev key code."""
    if len(key_name) == 1:
        if key_name in _SYMBOL_MAP:
            return getattr(ecodes, _SYMBOL_MAP[key_name])
        return getattr(ecodes, f"KEY_{key_name.upper()}")
    return getattr(ecodes, f"KEY_{key_name.upper()}")


class WaylandHotkeyListener:
    def __init__(self, callback, modifiers: set[str] = None, key: str = None):
        self._callback = callback
        self._modifiers = modifiers or {"ctrl", "shift"}
        self._key = key or ";"
        self._thread = None
        self._running = False
        self._last_press = 0.0
        self._pressed_keys: set[int] = set()

        # Build the set of modifier codes we need to track
        self._modifier_code_sets: dict[str, set[int]] = {}
        for mod in self._modifiers:
            self._modifier_code_sets[mod] = _MODIFIER_KEYS[mod]

        # All modifier codes flattened for quick lookup
        self._all_modifier_codes: set[int] = set()
        for codes in self._modifier_code_sets.values():
            self._all_modifier_codes |= codes

        self._target_key_code = _resolve_key_code(self._key)

    def _handle_event(self, event):
        """Process a single input event."""
        if event.type != ecodes.EV_KEY:
            return

        code = event.code
        value = event.value  # 1=down, 0=up, 2=repeat

        if value == 1:  # key down
            self._pressed_keys.add(code)
            if code == self._target_key_code:
                if self._check_modifiers():
                    now = time.monotonic()
                    if now - self._last_press >= _DEBOUNCE_SECONDS:
                        self._last_press = now
                        threading.Thread(
                            target=self._callback, daemon=True
                        ).start()
        elif value == 0:  # key up
            self._pressed_keys.discard(code)

    def _check_modifiers(self) -> bool:
        """Check if all required modifiers are currently pressed."""
        for mod, codes in self._modifier_code_sets.items():
            if not (self._pressed_keys & codes):
                return False
        return True

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            devices = [
                evdev.InputDevice(path) for path in evdev.list_devices()
            ]
        except PermissionError:
            logger.error(
                "Cannot access input devices. "
                "Add your user to the 'input' group: "
                "sudo usermod -aG input $USER"
            )
            return

        # Filter to keyboard devices
        keyboards = []
        for dev in devices:
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                keyboards.append(dev)
            else:
                dev.close()

        if not keyboards:
            logger.error("No keyboard devices found")
            return

        sel = selectors.DefaultSelector()
        for kb in keyboards:
            sel.register(kb, selectors.EVENT_READ)

        try:
            while self._running:
                events = sel.select(timeout=0.5)
                for key, _ in events:
                    device = key.fileobj
                    try:
                        for event in device.read():
                            self._handle_event(event)
                    except OSError:
                        sel.unregister(device)
                        device.close()
        finally:
            sel.close()
            for kb in keyboards:
                try:
                    kb.close()
                except Exception:
                    pass

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
