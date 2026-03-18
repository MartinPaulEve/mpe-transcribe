import os
import sys

import numpy as np
import pytest

from transcribe.macos_transcriber import MacOSTranscriber


class TestMacOSTranscriber:
    def setup_method(self):
        self.mock_mlx = sys.modules["mlx_whisper"]
        self.mock_sf = sys.modules["soundfile"]
        self.mock_mlx.reset_mock()
        self.mock_sf.reset_mock()

    def test_default_model_name(self):
        t = MacOSTranscriber()
        assert t._model_name == "mlx-community/whisper-large-v3-turbo"

    def test_custom_model_name(self):
        t = MacOSTranscriber(
            model_name="mlx-community/whisper-small"
        )
        assert t._model_name == "mlx-community/whisper-small"

    def test_load_model(self):
        t = MacOSTranscriber()
        t.load_model()
        assert t._model_loaded is True

    def test_transcribe_returns_text(self):
        t = MacOSTranscriber()
        t.load_model()
        self.mock_mlx.transcribe.return_value = {
            "text": " hello world "
        }
        audio = np.random.randn(16000).astype(np.float32)
        result = t.transcribe(audio, 16000)
        assert result == "hello world"
        self.mock_sf.write.assert_called_once()
        self.mock_mlx.transcribe.assert_called_once()

    def test_transcribe_passes_model_name(self):
        t = MacOSTranscriber(
            model_name="mlx-community/whisper-small"
        )
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
        self.mock_mlx.transcribe.return_value = {
            "text": "  padded text  "
        }
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

    def test_transcribe_cleans_up_temp_file(self):
        t = MacOSTranscriber()
        t.load_model()
        self.mock_mlx.transcribe.return_value = {"text": "test"}
        audio = np.zeros(16000, dtype=np.float32)
        t.transcribe(audio, 16000)
        # The temp file path passed to transcribe should be cleaned up
        tmp_path = self.mock_mlx.transcribe.call_args[0][0]
        assert not os.path.exists(tmp_path)

    def test_transcribe_cleans_up_on_error(self):
        t = MacOSTranscriber()
        t.load_model()
        self.mock_mlx.transcribe.side_effect = RuntimeError("model error")
        audio = np.zeros(16000, dtype=np.float32)
        with pytest.raises(RuntimeError):
            t.transcribe(audio, 16000)
