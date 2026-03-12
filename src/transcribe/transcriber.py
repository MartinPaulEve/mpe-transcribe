import os
import tempfile

os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"

import nemo.collections.asr as nemo_asr
import soundfile as sf

DEFAULT_MODEL = "nvidia/parakeet-tdt-0.6b-v3"


class Transcriber:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None

    def load_model(self):
        self._model = nemo_asr.models.ASRModel.from_pretrained(
            model_name=self._model_name
        )

    def transcribe(self, audio, sample_rate: int) -> str:
        if self._model is None:
            raise RuntimeError("model not loaded")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            sf.write(f, audio, sample_rate)
        try:
            result = self._model.transcribe([tmp_path])
            hypothesis = result[0]
            if isinstance(hypothesis, str):
                return hypothesis
            return hypothesis.text
        finally:
            os.unlink(tmp_path)
