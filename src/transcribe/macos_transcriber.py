import numpy as np

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


class MacOSTranscriber:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        initial_prompt: str | None = None,
    ):
        self._model_name = model_name
        self._initial_prompt = initial_prompt
        self._model_loaded = False

    def load_model(self):
        import mlx_whisper  # noqa: F401

        self._model_loaded = True

    def transcribe(self, audio, sample_rate: int) -> str:
        if not self._model_loaded:
            raise RuntimeError("model not loaded")
        import mlx_whisper

        # mlx_whisper accepts a numpy float32 array directly,
        # bypassing ffmpeg file decoding entirely.
        audio = np.asarray(audio, dtype=np.float32).flatten()
        kwargs = {"path_or_hf_repo": self._model_name}
        if self._initial_prompt:
            kwargs["initial_prompt"] = self._initial_prompt
        result = mlx_whisper.transcribe(audio, **kwargs)
        return result.get("text", "").strip()
