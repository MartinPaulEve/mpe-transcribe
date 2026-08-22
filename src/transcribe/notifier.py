import logging
import subprocess

logger = logging.getLogger(__name__)


class FilteredNotifier:
    """Wraps a platform notifier, silencing disabled channels."""

    def __init__(self, inner, visual: bool = True, sound: bool = True):
        self._inner = inner
        self._visual = visual
        self._sound = sound

    def notify(self, title: str, body: str):
        if self._visual:
            self._inner.notify(title, body)

    def ding(self):
        if self._sound:
            self._inner.ding()

    def notify_and_ding(self, title: str, body: str):
        self.notify(title, body)
        self.ding()


class AppNotifier:
    def notify(self, title: str, body: str):
        try:
            subprocess.run(["notify-send", title, body], check=False)
        except OSError as exc:
            logger.warning("Desktop notification unavailable: %s", exc)

    def ding(self):
        # Lazy import: client-mode installs have no sounddevice.
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError:
            return
        duration = 0.15
        sample_rate = 44100
        t = np.linspace(
            0, duration, int(sample_rate * duration), endpoint=False
        )
        tone = np.sin(2 * np.pi * 880 * t).astype(np.float32)
        sd.play(tone, samplerate=sample_rate)

    def notify_and_ding(self, title: str, body: str):
        self.notify(title, body)
        self.ding()
