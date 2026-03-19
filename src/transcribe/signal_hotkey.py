"""Hotkey listener that receives SIGUSR1 from the native launcher.

When Transcribe runs as a macOS launchd service, the C launcher
(transcribe-launcher) monitors the global hotkey via CGEventTap
and sends SIGUSR1 to the Python child when the hotkey is pressed.

This avoids the need for the Python process to have accessibility
permissions — the .app bundle's native executable has them instead.
"""

import logging
import signal
import threading

logger = logging.getLogger(__name__)


class SignalHotkeyListener:
    """Listens for SIGUSR1 and calls the callback on each signal."""

    def __init__(self, callback):
        self._callback = callback
        self._old_handler = None

    def _on_signal(self, signum, frame):
        logger.debug("SIGUSR1 received — toggling")
        threading.Thread(target=self._callback, daemon=True).start()

    def start(self):
        self._old_handler = signal.signal(signal.SIGUSR1, self._on_signal)
        logger.info("Hotkey listener: SIGUSR1 (from native launcher)")

    def stop(self):
        if self._old_handler is not None:
            signal.signal(signal.SIGUSR1, self._old_handler)
            self._old_handler = None
