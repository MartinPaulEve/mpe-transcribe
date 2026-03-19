import logging
import signal
import threading
from enum import Enum

import numpy as np

from transcribe.config import load_config, parse_hotkey
from transcribe.factory import (
    create_clipboard,
    create_hotkey_listener,
    create_notifier,
    create_transcriber,
)
from transcribe.recorder import AudioRecorder
from transcribe.session import detect_session

logger = logging.getLogger(__name__)

_PORTAUDIO_HINT = (
    "Check microphone permissions (macOS: System Settings → "
    "Privacy & Security → Microphone) and ensure no other app "
    "is using the mic."
)

# RMS below this threshold is treated as silence (mic not working
# or permissions denied — PortAudio returns zeros in that case).
_SILENCE_RMS_THRESHOLD = 1e-4


class AppState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


class TranscribeApp:
    def __init__(self, config: dict = None):
        self._config = config or load_config()
        self._state = AppState.IDLE
        self._recorder = AudioRecorder()
        self._transcriber = create_transcriber(self._config["model"])
        modifiers, key = parse_hotkey(self._config["hotkey"])
        self._hotkey = create_hotkey_listener(
            self.toggle, modifiers=modifiers, key=key
        )
        self._notifier = create_notifier()
        self._clipboard = create_clipboard()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    @property
    def state(self) -> AppState:
        return self._state

    def toggle(self):
        with self._lock:
            if self._state == AppState.IDLE:
                try:
                    self._start_recording()
                except Exception:
                    logger.exception(
                        "Failed to start recording. %s",
                        _PORTAUDIO_HINT,
                    )
                    self._notifier.notify("Transcribe", "Mic error — see logs")
                    self._state = AppState.IDLE
            elif self._state == AppState.RECORDING:
                self._stop_and_transcribe()

    def _start_recording(self):
        self._notifier.notify_and_ding("Transcribe", "Recording...")
        self._recorder.start()
        self._state = AppState.RECORDING
        logger.info("Recording started")

    def _stop_and_transcribe(self):
        audio = self._recorder.stop()
        logger.info(
            "Captured %d samples (%.1fs)",
            len(audio),
            len(audio) / 16000,
        )
        if len(audio) == 0:
            self._notifier.notify("Transcribe", "Recording too short")
            self._state = AppState.IDLE
            return
        rms = float(np.sqrt(np.mean(audio**2)))
        if rms < _SILENCE_RMS_THRESHOLD:
            logger.warning(
                "Recording is silent (RMS=%.2e). "
                "Microphone may not be working or permissions "
                "may be denied.",
                rms,
            )
            self._notifier.notify(
                "Transcribe",
                "No audio detected — check mic permissions",
            )
            self._state = AppState.IDLE
            return
        self._state = AppState.TRANSCRIBING
        self._notifier.notify_and_ding("Transcribe", "Transcribing...")
        logger.info("Recording stopped, transcribing...")
        thread = threading.Thread(target=self._do_transcribe, args=(audio,))
        thread.daemon = True
        thread.start()

    def _do_transcribe(self, audio):
        try:
            text = self._transcriber.transcribe(audio, 16000)
            if text:
                self._clipboard.paste_text(text)
                self._notifier.notify("Transcribe", "Pasted!")
            else:
                self._notifier.notify("Transcribe", "No speech detected")
        except Exception:
            logger.exception("Transcription failed")
            self._notifier.notify("Transcribe", "Transcription error")
        finally:
            self._state = AppState.IDLE

    def run(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        logger.info("Model: %s", self._config["model"])
        logger.info("Hotkey: %s", self._config["hotkey"])
        if detect_session() == "macos":
            from transcribe.macos_permissions import (
                warn_if_not_trusted,
            )

            warn_if_not_trusted()

        logger.info("Loading model...")
        self._transcriber.load_model()
        self._notifier.notify_and_ding("Transcribe", "Ready")
        logger.info(
            "Ready. Press %s to toggle recording. Ctrl+C to quit.",
            self._config["hotkey"],
        )
        self._hotkey.start()

        def _handle_signal(signum, frame):
            self._stop_event.set()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        self._stop_event.wait()
        self.shutdown()

    def shutdown(self):
        with self._lock:
            if self._state == AppState.RECORDING:
                try:
                    self._recorder.stop()
                except Exception:
                    pass
                self._state = AppState.IDLE
        self._hotkey.stop()
        logger.info("Shutdown complete")


def main():
    app = TranscribeApp()
    app.run()
