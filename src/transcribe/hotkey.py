import threading

from Xlib import XK, X
from Xlib import display as xdisplay

MODIFIER_MASKS = {
    "ctrl": X.ControlMask,
    "shift": X.ShiftMask,
    "alt": X.Mod1Mask,
    "super": X.Mod4Mask,
}

# Extra modifier bits (NumLock, CapsLock, ScrollLock) that we need to
# ignore when matching, otherwise the grab only fires when those are off.
_LOCK_MASKS = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]


def _keysym_for_name(name: str) -> int:
    """Resolve a key name to an X11 keysym."""
    if len(name) == 1:
        sym = XK.string_to_keysym(name)
        if sym == X.NoSymbol:
            # Single chars like ';' need XK lookup by name
            sym = ord(name)
        return sym
    sym = XK.string_to_keysym(name)
    if sym == X.NoSymbol:
        raise ValueError(f"Unknown key name: {name!r}")
    return sym


class HotkeyListener:
    def __init__(self, callback, modifiers: set[str] = None, key: str = None):
        self._callback = callback
        self._modifiers = modifiers or {"ctrl", "shift"}
        self._key = key or ";"
        self._thread = None
        self._display = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        self._display = xdisplay.Display()
        root = self._display.screen().root

        # Build the modifier mask
        mod_mask = 0
        for m in self._modifiers:
            mod_mask |= MODIFIER_MASKS[m]

        # Resolve key to keycode
        keysym = _keysym_for_name(self._key)
        keycode = self._display.keysym_to_keycode(keysym)

        # Grab with all combinations of lock masks so NumLock/CapsLock
        # don't prevent the grab from firing.
        for lock_mask in _LOCK_MASKS:
            root.grab_key(
                keycode,
                mod_mask | lock_mask,
                True,  # owner_events
                X.GrabModeAsync,
                X.GrabModeAsync,
            )

        self._display.flush()

        while self._running:
            event = self._display.next_event()
            if event.type == X.KeyPress:
                # Fire callback in a separate thread so the
                # X event loop is never blocked by slow work
                # (notifications, audio, transcription).
                threading.Thread(target=self._callback, daemon=True).start()

    def stop(self):
        self._running = False
        if self._display is not None:
            # Send a dummy event to unblock next_event()
            try:
                # Open a separate connection to poke the event loop
                dummy = xdisplay.Display()
                root = dummy.screen().root
                root.send_event(
                    X.KeyPress(
                        window=root,
                        detail=0,
                        state=0,
                        root_x=0,
                        root_y=0,
                        event_x=0,
                        event_y=0,
                        child=X.NONE,
                        root=root,
                        time=X.CurrentTime,
                        same_screen=True,
                    ),
                    event_mask=X.KeyPressMask,
                )
                dummy.flush()
                dummy.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
        if self._display is not None:
            try:
                self._display.close()
            except Exception:
                pass
            self._display = None
