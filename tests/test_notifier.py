import sys
from unittest.mock import patch

import numpy as np

from transcribe.notifier import AppNotifier, FilteredNotifier


class RecordingNotifier:
    """Test double capturing which channels actually fired."""

    def __init__(self):
        self.notifications = []
        self.dings = 0

    def notify(self, title, body):
        self.notifications.append((title, body))

    def ding(self):
        self.dings += 1

    def notify_and_ding(self, title, body):
        self.notify(title, body)
        self.ding()


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

    def test_notify_survives_missing_notify_send(self):
        with patch(
            "transcribe.notifier.subprocess.run",
            side_effect=FileNotFoundError(2, "No such file", "notify-send"),
        ):
            notifier = AppNotifier()
            notifier.notify("Title", "Body")  # must not raise

    def test_notify_and_ding_survives_missing_notify_send(self):
        with patch(
            "transcribe.notifier.subprocess.run",
            side_effect=FileNotFoundError(2, "No such file", "notify-send"),
        ):
            notifier = AppNotifier()
            notifier.notify_and_ding("Title", "Body")  # must not raise
        self.mock_sd.play.assert_called_once()


class TestFilteredNotifier:
    def test_defaults_pass_everything_through(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner)
        filtered.notify_and_ding("T", "B")
        assert inner.notifications == [("T", "B")]
        assert inner.dings == 1

    def test_visual_off_silences_notify(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, visual=False)
        filtered.notify("T", "B")
        assert inner.notifications == []

    def test_visual_off_keeps_sound(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, visual=False)
        filtered.notify_and_ding("T", "B")
        assert inner.notifications == []
        assert inner.dings == 1

    def test_sound_off_silences_ding(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, sound=False)
        filtered.ding()
        assert inner.dings == 0

    def test_sound_off_keeps_visual(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, sound=False)
        filtered.notify_and_ding("T", "B")
        assert inner.notifications == [("T", "B")]
        assert inner.dings == 0

    def test_both_off_silences_everything(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, visual=False, sound=False)
        filtered.notify_and_ding("T", "B")
        filtered.notify("T", "B")
        filtered.ding()
        assert inner.notifications == []
        assert inner.dings == 0


class TestFilteredNotifierEvents:
    def test_disabled_event_silences_notify_and_ding(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, events={"recording": False})
        filtered.notify_and_ding("T", "B", event="recording")
        assert inner.notifications == []
        assert inner.dings == 0

    def test_disabled_event_silences_notify(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, events={"error": False})
        filtered.notify("T", "B", event="error")
        assert inner.notifications == []

    def test_other_events_unaffected(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, events={"recording": False})
        filtered.notify_and_ding("T", "B", event="ready")
        assert inner.notifications == [("T", "B")]
        assert inner.dings == 1

    def test_unlisted_event_defaults_on(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, events={})
        filtered.notify_and_ding("T", "B", event="pasted")
        assert inner.notifications == [("T", "B")]
        assert inner.dings == 1

    def test_untagged_calls_ignore_event_flags(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, events={"ready": False})
        filtered.notify_and_ding("T", "B")
        assert inner.notifications == [("T", "B")]
        assert inner.dings == 1

    def test_master_visual_off_composes_with_event_on(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(
            inner, visual=False, events={"ready": True}
        )
        filtered.notify_and_ding("T", "B", event="ready")
        assert inner.notifications == []
        assert inner.dings == 1

    def test_master_sound_off_composes_with_event_on(self):
        inner = RecordingNotifier()
        filtered = FilteredNotifier(inner, sound=False, events={"ready": True})
        filtered.notify_and_ding("T", "B", event="ready")
        assert inner.notifications == [("T", "B")]
        assert inner.dings == 0
