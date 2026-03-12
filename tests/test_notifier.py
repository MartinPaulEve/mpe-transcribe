import sys
from unittest.mock import patch

import numpy as np

from transcribe.notifier import AppNotifier


class TestAppNotifier:
    def setup_method(self):
        self.mock_sd = sys.modules["sounddevice"]
        self.mock_sd.reset_mock()

    def test_notify_calls_notify_send(self):
        with patch("transcribe.notifier.subprocess") as mock_sub:
            notifier = AppNotifier()
            notifier.notify("Test Title", "Test Body")
            mock_sub.run.assert_called_once_with(
                ["notify-send", "Test Title", "Test Body"],
                check=False,
            )

    def test_ding_plays_tone(self):
        notifier = AppNotifier()
        notifier.ding()
        self.mock_sd.play.assert_called_once()
        args, kwargs = self.mock_sd.play.call_args
        tone = args[0]
        assert isinstance(tone, np.ndarray)
        assert tone.dtype == np.float32
        # 150ms at 44100Hz = ~6615 samples
        assert 6000 < len(tone) < 7000
        assert kwargs["samplerate"] == 44100

    def test_notify_and_ding_calls_both(self):
        with patch("transcribe.notifier.subprocess") as mock_sub:
            notifier = AppNotifier()
            notifier.notify_and_ding("Title", "Body")
            mock_sub.run.assert_called_once()
            self.mock_sd.play.assert_called_once()

    def test_ding_frequency_is_880hz(self):
        notifier = AppNotifier()
        notifier.ding()
        tone = self.mock_sd.play.call_args[0][0]
        fft = np.fft.rfft(tone)
        freqs = np.fft.rfftfreq(len(tone), 1.0 / 44100)
        peak_freq = freqs[np.argmax(np.abs(fft))]
        assert 870 < peak_freq < 890
