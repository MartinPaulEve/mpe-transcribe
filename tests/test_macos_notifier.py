import os
import subprocess
import sys
import wave
from unittest.mock import patch

import numpy as np

from tests.fake_sounddevice import FakeSoundDevice
from transcribe.macos_notifier import MacOSNotifier


class TestMacOSNotifier:
    def setup_method(self):
        self.mock_sd = sys.modules["sounddevice"]
        self.mock_sd.reset_mock()

    def test_notify_calls_osascript(self):
        with patch("transcribe.macos_notifier.subprocess") as mock_sub:
            notifier = MacOSNotifier()
            notifier.notify("Test Title", "Test Body")
            mock_sub.run.assert_called_once()
            cmd = mock_sub.run.call_args[0][0]
            assert cmd[0] == "osascript"
            assert "Test Title" in cmd[2]
            assert "Test Body" in cmd[2]

    def test_notify_uses_display_notification(self):
        with patch("transcribe.macos_notifier.subprocess") as mock_sub:
            notifier = MacOSNotifier()
            notifier.notify("Title", "Body")
            script = mock_sub.run.call_args[0][0][2]
            assert "display notification" in script

    def test_notify_does_not_raise_on_failure(self):
        with patch("transcribe.macos_notifier.subprocess") as mock_sub:
            mock_sub.run.side_effect = Exception("osascript failed")
            notifier = MacOSNotifier()
            # Should not raise
            notifier.notify("Title", "Body")

    def test_notify_bounds_subprocess_time(self):
        with patch("transcribe.macos_notifier.subprocess.run") as mock_run:
            notifier = MacOSNotifier()
            notifier.notify("Title", "Body")
            timeout = mock_run.call_args.kwargs.get("timeout")
            assert timeout is not None and timeout > 0

    def test_notify_survives_hung_osascript(self):
        with patch(
            "transcribe.macos_notifier.subprocess.run",
            side_effect=subprocess.TimeoutExpired("osascript", 5),
        ):
            notifier = MacOSNotifier()
            notifier.notify("Title", "Body")  # must not raise

    def _ding_command(self, mock_run):
        """The argv afplay was run with, or None if it was not run."""
        for call in mock_run.call_args_list:
            cmd = call[0][0]
            if cmd[0] == "afplay":
                return cmd
        return None

    def _read_wav(self, path):
        with wave.open(path, "rb") as wav:
            rate = wav.getframerate()
            assert wav.getnchannels() == 1
            assert wav.getsampwidth() == 2
            frames = wav.readframes(wav.getnframes())
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32)
        return rate, samples

    def test_ding_plays_a_sound_file_through_afplay(self):
        with patch("transcribe.macos_notifier.subprocess.run") as mock_run:
            MacOSNotifier().ding()
            cmd = self._ding_command(mock_run)
        assert cmd is not None
        assert os.path.isfile(cmd[-1])

    def test_ding_sound_is_a_short_880hz_tone(self):
        with patch("transcribe.macos_notifier.subprocess.run") as mock_run:
            MacOSNotifier().ding()
            cmd = self._ding_command(mock_run)
        rate, samples = self._read_wav(cmd[-1])
        # ~150 ms
        assert 0.1 < len(samples) / rate < 0.2
        fft = np.fft.rfft(samples)
        freqs = np.fft.rfftfreq(len(samples), 1.0 / rate)
        peak_freq = freqs[np.argmax(np.abs(fft))]
        assert 870 < peak_freq < 890

    def test_ding_does_not_use_portaudio(self):
        # PortAudio snapshots devices at init and chokes on Bluetooth
        # sample rates; the beep must go through the system's own
        # default-output routing instead.
        fake = FakeSoundDevice("speaker")
        with (
            patch("transcribe.macos_notifier.subprocess.run"),
            patch.dict(sys.modules, {"sounddevice": fake}),
        ):
            MacOSNotifier().ding()
        assert fake.played_on == []

    def test_ding_bounds_subprocess_time(self):
        with patch("transcribe.macos_notifier.subprocess.run") as mock_run:
            MacOSNotifier().ding()
            timeout = mock_run.call_args.kwargs.get("timeout")
        assert timeout is not None and timeout > 0

    def test_ding_survives_hung_afplay(self):
        with patch(
            "transcribe.macos_notifier.subprocess.run",
            side_effect=subprocess.TimeoutExpired("afplay", 5),
        ):
            MacOSNotifier().ding()  # must not raise

    def test_ding_survives_missing_afplay(self):
        with patch(
            "transcribe.macos_notifier.subprocess.run",
            side_effect=FileNotFoundError("afplay"),
        ):
            MacOSNotifier().ding()  # must not raise

    def test_ding_regenerates_a_deleted_sound_file(self):
        notifier = MacOSNotifier()
        with patch("transcribe.macos_notifier.subprocess.run") as mock_run:
            notifier.ding()
            path = self._ding_command(mock_run)[-1]
        os.remove(path)
        with patch("transcribe.macos_notifier.subprocess.run") as mock_run:
            notifier.ding()
            path = self._ding_command(mock_run)[-1]
        assert os.path.isfile(path)

    def test_notify_and_ding_does_both(self):
        with patch("transcribe.macos_notifier.subprocess.run") as mock_run:
            MacOSNotifier().notify_and_ding("Title", "Body")
            programs = {c[0][0][0] for c in mock_run.call_args_list}
        assert programs == {"osascript", "afplay"}
