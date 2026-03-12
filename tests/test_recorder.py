import sys

import numpy as np
import pytest

from transcribe.recorder import AudioRecorder


class TestAudioRecorder:
    def setup_method(self):
        self.mock_sd = sys.modules["sounddevice"]
        self.mock_sd.reset_mock()

    def test_initial_state_not_recording(self):
        recorder = AudioRecorder()
        assert recorder.is_recording is False

    def test_start_begins_recording(self):
        recorder = AudioRecorder()
        recorder.start()
        assert recorder.is_recording is True
        self.mock_sd.InputStream.assert_called_once()
        self.mock_sd.InputStream.return_value.start.assert_called_once()

    def test_stop_returns_audio_array(self):
        recorder = AudioRecorder()
        recorder.start()
        frame1 = np.ones((1024, 1), dtype=np.float32)
        frame2 = np.ones((1024, 1), dtype=np.float32) * 0.5
        recorder._frames.extend([frame1, frame2])
        result = recorder.stop()
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        assert result.ndim == 1
        assert len(result) == 2048
        self.mock_sd.InputStream.return_value.stop.assert_called_once()
        self.mock_sd.InputStream.return_value.close.assert_called_once()

    def test_stop_without_start_raises(self):
        recorder = AudioRecorder()
        with pytest.raises(RuntimeError, match="not recording"):
            recorder.stop()

    def test_double_start_raises(self):
        recorder = AudioRecorder()
        recorder.start()
        with pytest.raises(RuntimeError, match="already recording"):
            recorder.start()

    def test_callback_accumulates_frames(self):
        recorder = AudioRecorder()
        recorder.start()
        fake_data = np.random.randn(512, 1).astype(np.float32)
        recorder._callback(fake_data, 512, None, None)
        assert len(recorder._frames) == 1
        np.testing.assert_array_equal(recorder._frames[0], fake_data)

    def test_sample_rate_default(self):
        recorder = AudioRecorder()
        assert recorder.sample_rate == 16000

    def test_stop_clears_frames(self):
        recorder = AudioRecorder()
        recorder.start()
        recorder._frames.append(np.ones((100, 1), dtype=np.float32))
        recorder.stop()
        assert recorder.is_recording is False
