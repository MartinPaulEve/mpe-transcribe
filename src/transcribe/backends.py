"""Model registry mapping a model name to a configured transcriber.

This is the single extension point for adding new local models. To add
a future model:

1. If it uses the existing NeMo ``ASRModel`` interface and only needs
   different ``transcribe()`` arguments, add a ``(predicate, kwargs)``
   entry to ``_NEMO_PROFILES``.
2. If it needs a different load/inference path (e.g. a Whisper or a
   speech-LLM backend), write a backend class exposing the same
   ``load_model()`` / ``transcribe(audio, sample_rate)`` interface as
   ``Transcriber`` and add a rule below that builds it.

Builders lazy-import their backend so heavy dependencies load only when
the corresponding model is actually selected.
"""

# NeMo ASRModel-based profiles, checked in order. Each entry maps a
# predicate over the model name to the kwargs that model's
# ``transcribe()`` call needs. The final catch-all (``lambda _: True``)
# handles Parakeet and any other plain NeMo ASR model with a bare call.
_NEMO_PROFILES = [
    # Canary is a multilingual encoder-decoder and requires explicit
    # source/target languages; English-to-English keeps it verbatim.
    (
        lambda name: "canary-1b" in name,
        {
            "source_lang": "en",
            "target_lang": "en",
        },
    ),
    (lambda _: True, {}),
]


def build_transcriber(model_name: str, initial_prompt: str | None = None):
    """Return a transcriber configured for ``model_name``."""
    from transcribe.transcriber import Transcriber

    for matches, transcribe_kwargs in _NEMO_PROFILES:
        if matches(model_name):
            return Transcriber(
                model_name=model_name,
                transcribe_kwargs=transcribe_kwargs,
                initial_prompt=initial_prompt,
            )
    raise ValueError(f"No backend for model: {model_name!r}")
