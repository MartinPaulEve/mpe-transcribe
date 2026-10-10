import sys
from unittest.mock import patch

from tests.fake_sounddevice import FakeSoundDevice
from transcribe.audio_devices import refresh_devices


class TestRefreshDevices:
    def test_playback_after_refresh_uses_new_system_default(self):
        fake = FakeSoundDevice("speaker")
        fake.system_default = "headphones"
        with patch.dict(sys.modules, {"sounddevice": fake}):
            refresh_devices()
            fake.play(b"tone", samplerate=44100)
        assert fake.played_on == ["headphones"]

    def test_input_after_refresh_uses_new_system_default(self):
        fake = FakeSoundDevice("built-in mic")
        fake.system_default = "headset mic"
        with patch.dict(sys.modules, {"sounddevice": fake}):
            refresh_devices()
            fake.InputStream(samplerate=16000, channels=1)
        assert fake.opened_on == ["headset mic"]

    def test_leaves_portaudio_usable(self):
        fake = FakeSoundDevice()
        with patch.dict(sys.modules, {"sounddevice": fake}):
            refresh_devices()
            fake.play(b"tone", samplerate=44100)  # must not raise
        assert fake.initialized

    def test_in_flight_playback_is_closed_cleanly(self):
        fake = FakeSoundDevice()
        with patch.dict(sys.modules, {"sounddevice": fake}):
            fake.play(b"tone", samplerate=44100)  # a beep still sounding
            refresh_devices()
        assert fake.killed_streams == []
        assert fake.open_streams == set()

    def test_without_sounddevice_is_a_noop(self):
        with patch.dict(sys.modules, {"sounddevice": None}):
            refresh_devices()  # must not raise

    def test_survives_portaudio_error(self):
        fake = FakeSoundDevice()
        fake.fail_on_initialize = RuntimeError("PortAudio error")
        with patch.dict(sys.modules, {"sounddevice": fake}):
            refresh_devices()  # must not raise
