import logging
import signal
import threading
from enum import Enum

from transcribe.clipboard import Clipboard
from transcribe.config import load_config, parse_hotkey
from transcribe.hotkey import HotkeyListener
from transcribe.notifier import AppNotifier
from transcribe.recorder import AudioRecorder
from transcribe.transcriber import Transcriber

logger = logging.getLogger(__name__)


class AppState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


class TranscribeApp:
    def __init__(self, config: dict = None):
        self._config = config or load_config()
        self._state = AppState.IDLE
        self._recorder = AudioRecorder()
        self._transcriber = Transcriber(model_name=self._config["model"])
        modifiers, key = parse_hotkey(self._config["hotkey"])
        self._hotkey = HotkeyListener(
            self.toggle, modifiers=modifiers, key=key
        )
        self._notifier = AppNotifier()
        self._clipboard = Clipboard()
        self._lock = threading.Lock()

    @property
    def state(self) -> AppState:
        return self._state

    def toggle(self):
        with self._lock:
            if self._state == AppState.IDLE:
                self._start_recording()
            elif self._state == AppState.RECORDING:
                self._stop_and_transcribe()

    def _start_recording(self):
        self._recorder.start()
        self._state = AppState.RECORDING
        self._notifier.notify_and_ding("Transcribe", "Recording...")
        logger.info("Recording started")

    def _stop_and_transcribe(self):
        audio = self._recorder.stop()
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
        logging.basicConfig(level=logging.INFO)
        logger.info("Model: %s", self._config["model"])
        logger.info("Hotkey: %s", self._config["hotkey"])
        logger.info("Loading model...")
        self._transcriber.load_model()
        logger.info(
            "Ready. Press %s to toggle recording. Ctrl+C to quit.",
            self._config["hotkey"],
        )
        self._hotkey.start()
        try:
            signal.pause()
        except KeyboardInterrupt:
            pass
        self.shutdown()

    def shutdown(self):
        self._hotkey.stop()
        logger.info("Shutdown complete")


def main():
    app = TranscribeApp()
    app.run()
