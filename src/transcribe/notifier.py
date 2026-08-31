import logging
import queue
import subprocess
import threading

logger = logging.getLogger(__name__)

# Hard cap on any notification subprocess; a hung notification
# daemon must never stall the app.
SUBPROCESS_TIMEOUT = 5.0

# Beyond this many undelivered notifications the inner notifier is
# clearly stuck; drop new ones rather than grow without bound.
_QUEUE_LIMIT = 100


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


class AsyncNotifier:
    """Delivers a wrapped notifier's calls from a background thread.

    Platform notifiers shell out (notify-send, osascript) or touch
    audio devices; any of those can hang. Dispatching through a
    worker keeps a stuck notification from ever blocking the
    caller — in particular the network receive loops.
    """

    def __init__(self, inner):
        self.inner = inner
        self._queue = queue.SimpleQueue()
        self._worker = None
        self._start_lock = threading.Lock()

    def _ensure_worker(self):
        with self._start_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._drain, daemon=True
                )
                self._worker.start()

    def _drain(self):
        while True:
            method, args = self._queue.get()
            try:
                getattr(self.inner, method)(*args)
            except Exception:
                logger.exception("Notification failed")

    def _dispatch(self, method: str, *args):
        if self._queue.qsize() >= _QUEUE_LIMIT:
            logger.warning("Notification backlog full; dropping %s", method)
            return
        self._queue.put((method, args))
        self._ensure_worker()

    def notify(self, title: str, body: str):
        self._dispatch("notify", title, body)

    def ding(self):
        self._dispatch("ding")

    def notify_and_ding(self, title: str, body: str):
        self._dispatch("notify_and_ding", title, body)


class AppNotifier:
    def notify(self, title: str, body: str):
        try:
            subprocess.run(
                ["notify-send", title, body],
                check=False,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
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
