import logging
import math
import os
import struct
import subprocess
import tempfile
import wave

logger = logging.getLogger(__name__)

# Hard cap on any notification subprocess; a hung osascript or
# afplay must never stall the app.
SUBPROCESS_TIMEOUT = 5.0

_TONE_HZ = 880
_TONE_SECONDS = 0.15
_TONE_RATE = 44100
_TONE_FILENAME = "transcribe-ding.wav"


def _write_tone(path: str) -> None:
    """Write the ding as a 16-bit mono WAV using only the stdlib."""
    count = int(_TONE_RATE * _TONE_SECONDS)
    frames = bytearray()
    for i in range(count):
        sample = math.sin(2 * math.pi * _TONE_HZ * i / _TONE_RATE)
        frames += struct.pack("<h", int(sample * 32767 * 0.5))
    tmp = f"{path}.{os.getpid()}.tmp"
    with wave.open(tmp, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_TONE_RATE)
        wav.writeframes(bytes(frames))
    os.replace(tmp, path)


class MacOSNotifier:
    def notify(self, title: str, body: str):
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{body}" with title "{title}"',
                ],
                check=False,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except Exception:
            pass

    def ding(self):
        # Played by afplay rather than PortAudio: afplay is an ordinary
        # CoreAudio client, so it follows the system default output
        # (including a headset connected after launch) and lets the OS
        # resample for Bluetooth devices. PortAudio snapshots devices
        # at init and fails to open Bluetooth outputs at 44.1 kHz.
        try:
            path = self._tone_path()
            subprocess.run(
                ["afplay", path],
                check=False,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except Exception as exc:
            logger.warning("Audible ding unavailable: %s", exc)

    def _tone_path(self) -> str:
        path = os.path.join(tempfile.gettempdir(), _TONE_FILENAME)
        if not os.path.isfile(path):
            _write_tone(path)
        return path

    def notify_and_ding(self, title: str, body: str):
        self.notify(title, body)
        self.ding()
