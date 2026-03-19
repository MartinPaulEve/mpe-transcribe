import sys

import numpy as np
import pytest

from transcribe.macos_transcriber import MacOSTranscriber


class TestMacOSTranscriber:
    def setup_method(self):
        self.mock_mlx = sys.modules["mlx_whisper"]
        self.mock_mlx.reset_mock()

    def test_default_model_name(self):
        t = MacOSTranscriber()
        assert t._model_name == "mlx-community/whisper-large-v3-turbo"

    def test_custom_model_name(self):
        t = MacOSTranscriber(model_name="mlx-community/whisper-small")
        assert t._model_name == "mlx-community/whisper-small"

    def test_load_model(self):
        t = MacOSTranscriber()
        t.load_model()
        assert t._model_loaded is True

    def test_transcribe_returns_text(self):
        t = MacOSTranscriber()
        t.load_model()
        self.mock_mlx.transcribe.return_value = {"text": " hello world "}
        audio = np.random.randn(16000).astype(np.float32)
        result = t.transcribe(audio, 16000)
        assert result == "hello world"
        self.mock_mlx.transcribe.assert_called_once()

    def test_transcribe_passes_audio_array(self):
        t = MacOSTranscriber()
        t.load_model()
        self.mock_mlx.transcribe.return_value = {"text": "test"}
        audio = np.zeros(16000, dtype=np.float32)
        t.transcribe(audio, 16000)
        passed_audio = self.mock_mlx.transcribe.call_args[0][0]
        assert isinstance(passed_audio, np.ndarray)
        assert passed_audio.dtype == np.float32
        assert passed_audio.ndim == 1

    def test_transcribe_passes_model_name(self):
        t = MacOSTranscriber(model_name="mlx-community/whisper-small")
        t.load_model()
        self.mock_mlx.transcribe.return_value = {"text": "test"}
        audio = np.zeros(16000, dtype=np.float32)
        t.transcribe(audio, 16000)
        call_kwargs = self.mock_mlx.transcribe.call_args[1]
        assert call_kwargs["path_or_hf_repo"] == (
            "mlx-community/whisper-small"
        )

    def test_transcribe_without_load_raises(self):
        t = MacOSTranscriber()
        with pytest.raises(RuntimeError, match="model not loaded"):
            t.transcribe(np.zeros(100, dtype=np.float32), 16000)

    def test_transcribe_strips_whitespace(self):
        t = MacOSTranscriber()
        t.load_model()
        self.mock_mlx.transcribe.return_value = {"text": "  padded text  "}
        audio = np.zeros(16000, dtype=np.float32)
        result = t.transcribe(audio, 16000)
        assert result == "padded text"

    def test_transcribe_empty_text(self):
        t = MacOSTranscriber()
        t.load_model()
        self.mock_mlx.transcribe.return_value = {"text": ""}
        audio = np.zeros(16000, dtype=np.float32)
        result = t.transcribe(audio, 16000)
        assert result == ""

    def test_transcribe_flattens_multidim_audio(self):
        t = MacOSTranscriber()
        t.load_model()
        self.mock_mlx.transcribe.return_value = {"text": "test"}
        audio = np.zeros((16000, 1), dtype=np.float32)
        t.transcribe(audio, 16000)
        passed_audio = self.mock_mlx.transcribe.call_args[0][0]
        assert passed_audio.ndim == 1
        assert len(passed_audio) == 16000
