import os
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

from transcribe.transcriber import Transcriber


class TestTranscriber:
    def setup_method(self):
        self.mock_asr = sys.modules["nemo.collections.asr"]
        self.mock_sf = sys.modules["soundfile"]
        self.mock_asr.reset_mock()
        self.mock_sf.reset_mock()

    def test_load_model(self):
        t = Transcriber()
        mock_model = MagicMock()
        self.mock_asr.models.ASRModel.from_pretrained.return_value = mock_model
        t.load_model()
        self.mock_asr.models.ASRModel.from_pretrained.assert_called_once_with(
            model_name="nvidia/parakeet-tdt-0.6b-v3"
        )
        assert t._model is mock_model

    def test_load_model_custom_name(self):
        t = Transcriber(model_name="nvidia/parakeet-rnnt-1.1b")
        t.load_model()
        self.mock_asr.models.ASRModel.from_pretrained.assert_called_once_with(
            model_name="nvidia/parakeet-rnnt-1.1b"
        )

    def test_transcribe_returns_text(self):
        t = Transcriber()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ["hello world"]
        self.mock_asr.models.ASRModel.from_pretrained.return_value = mock_model
        t.load_model()

        audio = np.random.randn(16000).astype(np.float32)
        result = t.transcribe(audio, 16000)
        assert result == "hello world"
        self.mock_sf.write.assert_called_once()
        mock_model.transcribe.assert_called_once()

    def test_transcribe_without_load_raises(self):
        t = Transcriber()
        with pytest.raises(RuntimeError, match="model not loaded"):
            t.transcribe(np.zeros(100, dtype=np.float32), 16000)

    def test_sets_torch_env_var(self):
        assert os.environ.get("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD") == "1"
