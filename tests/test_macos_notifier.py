import sys
from unittest.mock import patch

import numpy as np

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

    def test_ding_plays_tone(self):
        notifier = MacOSNotifier()
        notifier.ding()
        self.mock_sd.play.assert_called_once()
        args, kwargs = self.mock_sd.play.call_args
        tone = args[0]
        assert isinstance(tone, np.ndarray)
        assert tone.dtype == np.float32
        # 150ms at 44100Hz = ~6615 samples
        assert 6000 < len(tone) < 7000
        assert kwargs["samplerate"] == 44100

    def test_ding_frequency_is_880hz(self):
        notifier = MacOSNotifier()
        notifier.ding()
        tone = self.mock_sd.play.call_args[0][0]
        fft = np.fft.rfft(tone)
        freqs = np.fft.rfftfreq(len(tone), 1.0 / 44100)
        peak_freq = freqs[np.argmax(np.abs(fft))]
        assert 870 < peak_freq < 890

    def test_notify_and_ding_calls_both(self):
        with patch("transcribe.macos_notifier.subprocess") as mock_sub:
            notifier = MacOSNotifier()
            notifier.notify_and_ding("Title", "Body")
            mock_sub.run.assert_called_once()
            self.mock_sd.play.assert_called_once()
