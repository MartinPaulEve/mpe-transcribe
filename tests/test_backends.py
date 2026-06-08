import sys
from unittest.mock import MagicMock

import numpy as np

from transcribe.backends import build_transcriber
from transcribe.transcriber import Transcriber


class TestBuildTranscriber:
    def setup_method(self):
        self.mock_asr = sys.modules["nemo.collections.asr"]
        self.mock_asr.reset_mock()

    def _load_and_transcribe(self, transcriber):
        mock_model = MagicMock()
        hypothesis = MagicMock()
        hypothesis.text = "hello world"
        mock_model.transcribe.return_value = [hypothesis]
        self.mock_asr.models.ASRModel.from_pretrained.return_value = mock_model
        transcriber.load_model()
        audio = np.zeros(16000, dtype=np.float32)
        text = transcriber.transcribe(audio, 16000)
        return text, mock_model

    def test_parakeet_returns_nemo_transcriber(self):
        t = build_transcriber("nvidia/parakeet-tdt-0.6b-v3")
        assert isinstance(t, Transcriber)

    def test_parakeet_transcribes_without_language_kwargs(self):
        t = build_transcriber("nvidia/parakeet-tdt-0.6b-v3")
        text, mock_model = self._load_and_transcribe(t)
        assert text == "hello world"
        assert mock_model.transcribe.call_args.kwargs == {}

    def test_canary_returns_nemo_transcriber(self):
        t = build_transcriber("nvidia/canary-1b-v2")
        assert isinstance(t, Transcriber)

    def test_canary_requests_english_source_and_target(self):
        t = build_transcriber("nvidia/canary-1b-v2")
        text, mock_model = self._load_and_transcribe(t)
        assert text == "hello world"
        assert mock_model.transcribe.call_args.kwargs == {
            "source_lang": "en",
            "target_lang": "en",
        }

    def test_unknown_model_falls_back_to_bare_call(self):
        t = build_transcriber("nvidia/some-future-asr-model")
        _, mock_model = self._load_and_transcribe(t)
        assert mock_model.transcribe.call_args.kwargs == {}
