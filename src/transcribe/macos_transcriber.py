import os
import tempfile

import soundfile as sf

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


class MacOSTranscriber:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model_loaded = False

    def load_model(self):
        import mlx_whisper  # noqa: F401

        self._model_loaded = True

    def transcribe(self, audio, sample_rate: int) -> str:
        if not self._model_loaded:
            raise RuntimeError("model not loaded")
        import mlx_whisper

        with tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False
        ) as f:
            tmp_path = f.name
            sf.write(f, audio, sample_rate)
        try:
            result = mlx_whisper.transcribe(
                tmp_path,
                path_or_hf_repo=self._model_name,
            )
            return result.get("text", "").strip()
        finally:
            os.unlink(tmp_path)
