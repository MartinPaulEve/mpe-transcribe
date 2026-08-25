import logging
import subprocess

logger = logging.getLogger(__name__)


class FilteredNotifier:
    """Wraps a platform notifier, silencing disabled channels.

    The master switches (visual/sound) silence one channel for
    every event; a per-event flag set to False silences both
    channels for that event. Untagged calls (event=None) are
    governed by the masters alone.
    """

    def __init__(
        self,
        inner,
        visual: bool = True,
        sound: bool = True,
        events: dict | None = None,
    ):
        self._inner = inner
        self._visual = visual
        self._sound = sound
        self._events = dict(events or {})

    def _event_on(self, event: str | None) -> bool:
        return event is None or self._events.get(event, True)

    def notify(self, title: str, body: str, event: str | None = None):
        if self._visual and self._event_on(event):
            self._inner.notify(title, body)

    def ding(self, event: str | None = None):
        if self._sound and self._event_on(event):
            self._inner.ding()

    def notify_and_ding(self, title: str, body: str, event: str | None = None):
        self.notify(title, body, event=event)
        self.ding(event=event)


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
