import argparse
import logging
import signal
import threading
from enum import Enum

from transcribe.config import load_config, parse_hotkey, resolve_psk
from transcribe.corrections import apply_corrections, build_whisper_prompt
from transcribe.device_check import check_default_input_device
from transcribe.factory import (
    create_clipboard,
    create_hotkey_listener,
    create_notifier,
    create_transcriber,
)
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

_LOG_FORMAT = "%(asctime)s %(levelname)s:%(name)s:%(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _make_recorder():
    # Imported lazily so client mode never needs sounddevice.
    from transcribe.recorder import AudioRecorder

    return AudioRecorder()


def _is_silent(audio) -> bool:
    import numpy as np

    rms = float(np.sqrt(np.mean(audio**2)))
    if rms < _SILENCE_RMS_THRESHOLD:
        logger.warning(
            "Recording is silent (RMS=%.2e). "
            "Microphone may not be working or permissions "
            "may be denied.",
            rms,
        )
        return True
    return False


def _warn_if_macos_untrusted():
    if detect_session() == "macos":
        from transcribe.macos_permissions import warn_if_not_trusted

        warn_if_not_trusted()


class AppState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


class TranscribeApp:
    def __init__(self, config: dict = None):
        self._config = config or load_config()
        self._state = AppState.IDLE
        self._recorder = _make_recorder()
        prompt = build_whisper_prompt(
            replacements=self._config.get("replacements"),
            custom_terms=self._config.get("custom_terms"),
        )
        self._transcriber = create_transcriber(
            self._config["model"], initial_prompt=prompt
        )
        modifiers, key = parse_hotkey(self._config["hotkey"])
        self._hotkey = create_hotkey_listener(
            self.toggle, modifiers=modifiers, key=key
        )
        notifications = self._config.get("notifications", {})
        self._notifier = create_notifier(**notifications)
        self._clipboard = create_clipboard(
            paste_method=self._config.get("paste_method", "ctrl+v")
        )
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
        ok, msg = check_default_input_device()
        if not ok:
            logger.error("Device check failed: %s", msg)
            self._notifier.notify("Transcribe", msg)
            self._state = AppState.IDLE
            return
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
        if _is_silent(audio):
            self._notifier.notify(
                "Transcribe",
                "No audio detected — check mic permissions",
            )
            self._state = AppState.IDLE
            return
        self._state = AppState.TRANSCRIBING
        self._notifier.notify_and_ding(
            "Transcribe", "Stopped — transcribing..."
        )
        logger.info("Recording stopped, transcribing...")
        thread = threading.Thread(target=self._do_transcribe, args=(audio,))
        thread.daemon = True
        thread.start()

    def _do_transcribe(self, audio):
        try:
            text = self._transcriber.transcribe(audio, 16000)
            if text:
                original = text
                text = apply_corrections(
                    text,
                    replacements=self._config.get("replacements"),
                    custom_terms=self._config.get("custom_terms"),
                    threshold=self._config.get("custom_terms_threshold", 0.8),
                )
                if text != original:
                    logger.info(
                        "Corrections applied: %r -> %r",
                        original,
                        text,
                    )
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
            format=_LOG_FORMAT,
            datefmt=_LOG_DATEFMT,
        )
        logger.info("Model: %s", self._config["model"])
        logger.info("Hotkey: %s", self._config["hotkey"])
        _warn_if_macos_untrusted()

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


class HostApp:
    """host mode: record + transcribe here, triggered by clients.

    The network Host drives this app's recorder/transcriber through
    its on_start/on_stop callbacks; completed text is published back
    to the initiating client instead of (or in addition to) being
    pasted locally.
    """

    def __init__(self, config: dict = None, transport=None):
        self._config = config or load_config()
        self._network = self._config["network"]
        psk = resolve_psk(self._network)
        self._recorder = _make_recorder()
        prompt = build_whisper_prompt(
            replacements=self._config.get("replacements"),
            custom_terms=self._config.get("custom_terms"),
        )
        self._transcriber = create_transcriber(
            self._config["model"], initial_prompt=prompt
        )
        notifications = self._config.get("notifications", {})
        self._notifier = create_notifier(**notifications)
        self._clipboard = None
        if self._network["also_paste_locally"] or self._network["host_hotkey"]:
            self._clipboard = create_clipboard(
                paste_method=self._config.get("paste_method", "ctrl+v")
            )
        if transport is None:
            from transcribe.net.transport import UdpTransport

            transport = UdpTransport(
                (self._network["bind_host"], self._network["bind_port"])
            )
        self._transport = transport
        from transcribe.net.host import Host

        self.host = Host(
            self._network,
            psk,
            transport,
            on_start=self._start_recording,
            on_stop=self._stop_and_transcribe,
        )
        self._hotkey = None
        if self._network["host_hotkey"]:
            modifiers, key = parse_hotkey(self._config["hotkey"])
            self._hotkey = create_hotkey_listener(
                self._toggle, modifiers=modifiers, key=key
            )
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def _toggle(self):
        with self._lock:
            if self.host.state == "idle":
                self.host.local_start()
            elif self.host.state == "recording":
                self.host.local_stop()

    def _start_recording(self):
        # Host callback: raising aborts the session cleanly.
        ok, msg = check_default_input_device()
        if not ok:
            logger.error("Device check failed: %s", msg)
            self._notifier.notify("Transcribe", msg)
            raise RuntimeError(msg)
        self._notifier.notify_and_ding("Transcribe", "Recording...")
        self._recorder.start()
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
            self.host.finish_session()
            return
        if _is_silent(audio):
            self._notifier.notify(
                "Transcribe",
                "No audio detected — check mic permissions",
            )
            self.host.finish_session()
            return
        self._notifier.notify_and_ding(
            "Transcribe", "Stopped — transcribing..."
        )
        local = self.host.initiator_addr is None
        thread = threading.Thread(
            target=self._do_transcribe, args=(audio, local)
        )
        thread.daemon = True
        thread.start()

    def _do_transcribe(self, audio, local: bool):
        try:
            text = self._transcriber.transcribe(audio, 16000)
            if text:
                text = apply_corrections(
                    text,
                    replacements=self._config.get("replacements"),
                    custom_terms=self._config.get("custom_terms"),
                    threshold=self._config.get("custom_terms_threshold", 0.8),
                )
            if text:
                with self._lock:
                    self.host.publish_text(text)
                    if self._clipboard is not None and (
                        local or self._network["also_paste_locally"]
                    ):
                        logger.info(
                            "Pasting locally on the host too "
                            "(local=%s also_paste_locally=%s)",
                            local,
                            self._network["also_paste_locally"],
                        )
                        self._clipboard.paste_text(text)
                self._notifier.notify("Transcribe", "Sent!")
            else:
                self._notifier.notify("Transcribe", "No speech detected")
        except Exception:
            logger.exception("Transcription failed")
            self._notifier.notify("Transcribe", "Transcription error")
            with self._lock:
                self.host.publish_state("error")
        finally:
            with self._lock:
                self.host.finish_session()

    def run(self):
        logging.basicConfig(
            level=logging.INFO,
            format=_LOG_FORMAT,
            datefmt=_LOG_DATEFMT,
        )
        logger.info("Model: %s", self._config["model"])
        logger.info(
            "Host mode: listening on %s:%d",
            self._network["bind_host"],
            self._network["bind_port"],
        )
        logger.info(
            "Host flags: also_paste_locally=%s host_hotkey=%s deliver_to=%s",
            self._network["also_paste_locally"],
            self._network["host_hotkey"],
            self._network["deliver_to"],
        )
        _warn_if_macos_untrusted()
        logger.info("Loading model...")
        self._transcriber.load_model()
        self._notifier.notify_and_ding("Transcribe", "Ready")
        if self._hotkey is not None:
            self._hotkey.start()

        def _handle_signal(signum, frame):
            self._stop_event.set()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        while not self._stop_event.is_set():
            result = self._transport.recvfrom()
            with self._lock:
                if result is not None:
                    self.host.handle_datagram(*result)
                self.host.tick()
        self.shutdown()

    def shutdown(self):
        with self._lock:
            if self.host.state == "recording":
                try:
                    self._recorder.stop()
                except Exception:
                    pass
                self.host.finish_session()
        if self._hotkey is not None:
            self._hotkey.stop()
        self._transport.close()
        logger.info("Shutdown complete")


class ClientApp:
    """client mode: hotkey + paste only; the host transcribes.

    No recorder, no transcriber, no model — just the platform
    hotkey/notifier/clipboard backends wired to the network Client.
    """

    def __init__(self, config: dict = None, transport=None):
        self._config = config or load_config()
        self._network = self._config["network"]
        psk = resolve_psk(self._network)
        if transport is None:
            from transcribe.net.transport import UdpTransport

            transport = UdpTransport(("0.0.0.0", 0))
        self._transport = transport
        from transcribe.net.client import Client

        self.client = Client(
            self._network,
            psk,
            transport,
            on_state=self._on_state,
            on_text=self._on_text,
        )
        modifiers, key = parse_hotkey(self._config["hotkey"])
        self._hotkey = create_hotkey_listener(
            self._trigger, modifiers=modifiers, key=key
        )
        notifications = self._config.get("notifications", {})
        self._notifier = create_notifier(**notifications)
        self._clipboard = create_clipboard(
            paste_method=self._config.get("paste_method", "ctrl+v")
        )
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def _trigger(self):
        with self._lock:
            self.client.trigger()

    def _on_state(self, body: dict):
        state = body.get("state")
        if state == "recording":
            self._notifier.notify_and_ding("Transcribe", "Recording...")
        elif state == "transcribing":
            self._notifier.notify_and_ding(
                "Transcribe", "Stopped — transcribing..."
            )
        elif state == "error":
            self._notifier.notify("Transcribe", "Transcription error")

    def _on_text(self, text: str):
        logger.info("Text received (%d chars); pasting", len(text))
        self._clipboard.paste_text(text)
        logger.info("Paste complete")
        self._notifier.notify("Transcribe", "Pasted!")

    def run(self):
        logging.basicConfig(
            level=logging.INFO,
            format=_LOG_FORMAT,
            datefmt=_LOG_DATEFMT,
        )
        logger.info(
            "Client mode: host %s:%d, hotkey %s",
            self._network["server_host"],
            self._network["server_port"],
            self._config["hotkey"],
        )
        logger.info(
            "Session: %s; hotkey listener: %s; clipboard: %s",
            detect_session(),
            type(self._hotkey).__name__,
            type(self._clipboard).__name__,
        )
        self._notifier.notify_and_ding("Transcribe", "Ready")
        with self._lock:
            self.client.start()
        self._hotkey.start()

        def _handle_signal(signum, frame):
            self._stop_event.set()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        while not self._stop_event.is_set():
            result = self._transport.recvfrom()
            with self._lock:
                if result is not None:
                    self.client.handle_datagram(*result)
                self.client.tick()
        self.shutdown()

    def shutdown(self):
        try:
            with self._lock:
                self.client.stop()
        except Exception:
            pass
        self._hotkey.stop()
        self._transport.close()
        logger.info("Shutdown complete")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="transcribe",
        description="Voice transcription with a global hotkey.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["keygen"],
        help="keygen: print a fresh base64 pre-shared key",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--standalone",
        action="store_true",
        help="record, transcribe, and paste locally (default)",
    )
    mode_group.add_argument(
        "--host",
        action="store_true",
        help="record + transcribe here, serve clients over UDP",
    )
    mode_group.add_argument(
        "--client",
        action="store_true",
        help="hotkey + paste only; a remote host transcribes",
    )
    parser.add_argument("--server-host", help="host address (client mode)")
    parser.add_argument(
        "--server-port", type=int, help="host UDP port (client mode)"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    if args.command == "keygen":
        from transcribe.net import crypto

        print(crypto.encode_key(crypto.generate_key()))
        return
    config = load_config()
    network = config["network"]
    if args.host:
        network["mode"] = "host"
    elif args.client:
        network["mode"] = "client"
    elif args.standalone:
        network["mode"] = "standalone"
    if args.server_host:
        network["server_host"] = args.server_host
    if args.server_port:
        network["server_port"] = args.server_port
    mode = network["mode"]
    if mode == "host":
        app = HostApp(config)
    elif mode == "client":
        app = ClientApp(config)
    else:
        app = TranscribeApp(config)
    app.run()
